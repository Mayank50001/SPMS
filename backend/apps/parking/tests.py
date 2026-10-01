"""Model tests for the parking catalogue (increment 3.1).

Note: ``0002_seed_cities`` is a data migration, so Django applies it when it
builds the test database and the seeded cities (BLR, DEL, ...) are present before
any test runs. Each class therefore clears the table and creates its own data,
so the tests never assert against production seed data or assume an empty table.
"""

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User

from .models import City, ParkingLot, ParkingSlot


class CityModelTests(TestCase):
    def setUp(self):
        # No lots exist yet, so PROTECT does not block this.
        City.objects.all().delete()

    def test_code_is_normalised_to_upper_and_trimmed(self):
        city = City.objects.create(code="  blr ", name="Bengaluru")
        self.assertEqual(city.code, "BLR")

    def test_code_must_be_unique(self):
        City.objects.create(code="BLR", name="Bengaluru")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                City.objects.create(code="BLR", name="Another")

    def test_str_includes_name_and_code(self):
        city = City.objects.create(code="DEL", name="Delhi")
        self.assertEqual(str(city), "Delhi (DEL)")


class ParkingLotModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        cls.blr = City.objects.create(code="BLR", name="Bengaluru")
        cls.delhi = City.objects.create(code="DEL", name="Delhi")

    def test_code_is_derived_from_city_and_number(self):
        lot = ParkingLot.objects.create(
            city=self.blr, number=7, name="MG Road", address_line="MG Road 1"
        )
        self.assertEqual(lot.code, "BLR-007")

    def test_client_supplied_code_is_ignored(self):
        lot = ParkingLot.objects.create(
            city=self.blr, number=8, name="X", address_line="Y", code="HACK-999"
        )
        self.assertEqual(lot.code, "BLR-008")

    def test_same_number_in_different_cities_is_allowed(self):
        ParkingLot.objects.create(city=self.blr, number=1, name="A", address_line="a")
        ParkingLot.objects.create(city=self.delhi, number=1, name="B", address_line="b")
        self.assertEqual(ParkingLot.objects.count(), 2)

    def test_number_is_unique_within_a_city(self):
        ParkingLot.objects.create(city=self.blr, number=1, name="A", address_line="a")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ParkingLot.objects.create(
                    city=self.blr, number=1, name="B", address_line="b"
                )

    def test_defaults(self):
        lot = ParkingLot.objects.create(
            city=self.blr, number=2, name="A", address_line="a"
        )
        self.assertTrue(lot.is_active)
        self.assertIsNone(lot.manager)

    def test_city_with_lots_cannot_be_deleted(self):
        ParkingLot.objects.create(city=self.blr, number=3, name="A", address_line="a")
        with self.assertRaises(ProtectedError):
            self.blr.delete()

class ParkingApiTests(TestCase):
    """API surface and permissions for cities and lots (D37)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        cls.city = City.objects.create(code="BLR", name="Bengaluru")
        cls.consumer = User.objects.create_user(
            email="consumer@example.com", password="Tr0ub4dor&3", full_name="Consumer"
        )
        cls.manager = User.objects.create_user(
            email="manager@example.com",
            password="Tr0ub4dor&3",
            full_name="Manager",
            role=User.Role.MANAGER,
        )
        cls.admin = User.objects.create_user(
            email="admin@example.com",
            password="Tr0ub4dor&3",
            full_name="Admin",
            role=User.Role.ADMIN,
        )
        cls.active = ParkingLot.objects.create(
            city=cls.city, number=1, name="MG Road", address_line="MG Road 1"
        )
        cls.inactive = ParkingLot.objects.create(
            city=cls.city,
            number=2,
            name="Closed",
            address_line="Closed 2",
            is_active=False,
        )

    def setUp(self):
        self.client = APIClient()

    def _login(self, user):
        self.client.force_authenticate(user=user)

    # --- public reads ---------------------------------------------------

    def test_anonymous_can_list_active_lots(self):
        response = self.client.get("/api/parking-lots/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([lot["code"] for lot in response.data], ["BLR-001"])

    def test_anonymous_gets_404_for_inactive_lot(self):
        response = self.client.get(f"/api/parking-lots/{self.inactive.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_sees_inactive_lot(self):
        self._login(self.admin)
        response = self.client.get(f"/api/parking-lots/{self.inactive.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_by_city_code_and_search(self):
        response = self.client.get("/api/parking-lots/?city=blr&search=MG")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    # --- writes are Administrator-only ---------------------------------

    def test_anonymous_cannot_create_lot(self):
        response = self.client.post("/api/parking-lots/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_consumer_and_manager_cannot_create_lot(self):
        for user in (self.consumer, self.manager):
            self._login(user)
            response = self.client.post("/api/parking-lots/", {}, format="json")
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_creates_lot_and_code_is_derived(self):
        self._login(self.admin)
        payload = {
            "city_code": "blr",  # lower-case on purpose
            "number": 7,
            "name": "New Lot",
            "address_line": "Road 7",
        }
        response = self.client.post("/api/parking-lots/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["code"], "BLR-007")
        self.assertTrue(response.data["is_active"])

    def test_duplicate_number_in_city_is_rejected(self):
        self._login(self.admin)
        payload = {
            "city_code": "BLR",
            "number": 1,  # already used by self.active
            "name": "Dup",
            "address_line": "Dup 1",
        }
        response = self.client.post("/api/parking-lots/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("number", response.data)

    def test_unknown_city_code_is_rejected(self):
        self._login(self.admin)
        payload = {"city_code": "ZZZ", "number": 9, "name": "X", "address_line": "Y"}
        response = self.client.post("/api/parking-lots/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("city_code", response.data)

    def test_admin_can_assign_a_manager(self):
        self._login(self.admin)
        response = self.client.patch(
            f"/api/parking-lots/{self.active.id}/",
            {"manager": self.manager.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.active.refresh_from_db()
        self.assertEqual(self.active.manager_id, self.manager.id)

    def test_non_manager_cannot_be_assigned(self):
        self._login(self.admin)
        response = self.client.patch(
            f"/api/parking-lots/{self.active.id}/",
            {"manager": self.consumer.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("manager", response.data)

    def test_delete_and_put_are_not_allowed(self):
        self._login(self.admin)
        self.assertEqual(
            self.client.delete(f"/api/parking-lots/{self.active.id}/").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.put(
                f"/api/parking-lots/{self.active.id}/", {}, format="json"
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    # --- cities ---------------------------------------------------------

    def test_cities_are_publicly_listable(self):
        response = self.client.get("/api/cities/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([c["code"] for c in response.data], ["BLR"])

    def test_only_admin_can_create_a_city(self):
        self._login(self.consumer)
        response = self.client.post(
            "/api/cities/", {"code": "MAA", "name": "Chennai"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self._login(self.admin)
        response = self.client.post(
            "/api/cities/", {"code": "MAA", "name": "Chennai"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["code"], "MAA")

    def test_duplicate_city_code_is_rejected_case_insensitively(self):
        self._login(self.admin)
        response = self.client.post(
            "/api/cities/", {"code": "blr", "name": "Dup"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)

class ParkingSlotModelTests(TestCase):
    """Model rules for slots (increment 3.2)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        cls.city = City.objects.create(code="BLR", name="Bengaluru")
        cls.lot = ParkingLot.objects.create(
            city=cls.city, number=1, name="MG Road", address_line="MG Road 1"
        )
        cls.other_lot = ParkingLot.objects.create(
            city=cls.city, number=2, name="Other", address_line="Other 2"
        )

    def test_defaults(self):
        slot = ParkingSlot.objects.create(lot=self.lot, number="A-01")
        self.assertEqual(slot.slot_type, ParkingSlot.SlotType.REGULAR)
        self.assertEqual(slot.status, ParkingSlot.Status.AVAILABLE)
        self.assertEqual(slot.floor, "")

    def test_number_is_canonicalised(self):
        slot = ParkingSlot.objects.create(lot=self.lot, number="  a-01 ")
        self.assertEqual(slot.number, "A-01")

    def test_number_is_unique_within_a_lot(self):
        ParkingSlot.objects.create(lot=self.lot, number="A-01")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ParkingSlot.objects.create(lot=self.lot, number="A-01")

    def test_same_number_in_different_lots_is_allowed(self):
        ParkingSlot.objects.create(lot=self.lot, number="A-01")
        ParkingSlot.objects.create(lot=self.other_lot, number="A-01")
        self.assertEqual(ParkingSlot.objects.count(), 2)

    def test_deleting_a_lot_cascades_to_its_slots(self):
        ParkingSlot.objects.create(lot=self.lot, number="A-01")
        self.lot.delete()
        self.assertEqual(ParkingSlot.objects.count(), 0)

    def test_str_includes_lot_code_and_number(self):
        slot = ParkingSlot.objects.create(lot=self.lot, number="A-01")
        self.assertEqual(str(slot), "BLR-001 - A-01")

class ParkingSlotApiTests(TestCase):
    """Slot API surface, lot scoping and Invariant 3 (increment 3.2)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        cls.city = City.objects.create(code="BLR", name="Bengaluru")

        cls.consumer = User.objects.create_user(
            email="consumer@example.com",
            password="Tr0ub4dor&3",
            full_name="Consumer",
        )
        cls.manager = User.objects.create_user(
            email="manager@example.com",
            password="Tr0ub4dor&3",
            full_name="Manager",
            role=User.Role.MANAGER,
        )
        cls.other_manager = User.objects.create_user(
            email="other@example.com",
            password="Tr0ub4dor&3",
            full_name="Other",
            role=User.Role.MANAGER,
        )
        cls.admin = User.objects.create_user(
            email="admin@example.com",
            password="Tr0ub4dor&3",
            full_name="Admin",
            role=User.Role.ADMIN,
        )

        cls.lot = ParkingLot.objects.create(
            city=cls.city, number=1, name="MG Road", address_line="MG Road 1",
            manager=cls.manager,
        )
        cls.inactive_lot = ParkingLot.objects.create(
            city=cls.city, number=2, name="Closed", address_line="Closed 2",
            manager=cls.manager, is_active=False,
        )
        cls.other_lot = ParkingLot.objects.create(
            city=cls.city, number=3, name="Other", address_line="Other 3",
            manager=cls.other_manager,
        )
        cls.slot = ParkingSlot.objects.create(lot=cls.lot, number="A-01")

    def setUp(self):
        self.client = APIClient()

    def _login(self, user):
        self.client.force_authenticate(user=user)

    def _slots_url(self, lot):
        return f"/api/parking-lots/{lot.id}/slots/"

    def _slot_url(self, lot, slot):
        return f"/api/parking-lots/{lot.id}/slots/{slot.id}/"

    def test_anonymous_can_list_slots_of_an_active_lot(self):
        response = self.client.get(self._slots_url(self.lot))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([s["number"] for s in response.data], ["A-01"])

    def test_anonymous_gets_404_for_slots_of_an_inactive_lot(self):
        response = self.client.get(self._slots_url(self.inactive_lot))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_manager_can_read_slots_of_an_assigned_inactive_lot(self):
        self._login(self.manager)
        response = self.client.get(self._slots_url(self.inactive_lot))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_listing_returns_only_that_lots_slots(self):
        ParkingSlot.objects.create(lot=self.other_lot, number="B-01")
        response = self.client.get(self._slots_url(self.lot))
        self.assertEqual([s["number"] for s in response.data], ["A-01"])

    # --- writes: Admin or the lot's Manager -----------------------------

    def test_anonymous_cannot_create_slot(self):
        response = self.client.post(self._slots_url(self.lot), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_consumer_cannot_create_slot(self):
        self._login(self.consumer)
        response = self.client.post(self._slots_url(self.lot), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassigned_manager_gets_404(self):
        self._login(self.other_manager)
        payload = {"number": "Z-09", "slot_type": "REGULAR"}
        response = self.client.post(self._slots_url(self.lot), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_assigned_manager_can_create_slot(self):
        self._login(self.manager)
        payload = {"number": "A-02", "floor": "G", "slot_type": "EV"}
        response = self.client.post(self._slots_url(self.lot), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["number"], "A-02")
        self.assertEqual(response.data["slot_type"], "EV")
        self.assertEqual(response.data["status"], "AVAILABLE")
        self.assertEqual(response.data["lot_code"], "BLR-001")

    def test_admin_can_create_slot_and_defaults_apply(self):
        self._login(self.admin)
        response = self.client.post(
            self._slots_url(self.lot), {"number": "A-03"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["slot_type"], "REGULAR")
        self.assertEqual(response.data["status"], "AVAILABLE")

    def test_duplicate_number_in_lot_is_rejected(self):
        self._login(self.admin)
        # Lower-case "a-01" proves canonicalisation feeds the duplicate check.
        response = self.client.post(
            self._slots_url(self.lot), {"number": "a-01"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("number", response.data)

    def test_same_number_in_another_lot_is_allowed(self):
        self._login(self.admin)
        response = self.client.post(
            self._slots_url(self.other_lot), {"number": "A-01"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_invalid_slot_type_is_rejected(self):
        self._login(self.admin)
        response = self.client.post(
            self._slots_url(self.lot),
            {"number": "A-04", "slot_type": "SPACESHIP"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("slot_type", response.data)

    def test_blank_number_is_rejected(self):
        self._login(self.admin)
        response = self.client.post(
            self._slots_url(self.lot), {"number": "   "}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("number", response.data)

    # --- status changes -------------------------------------------------

    def test_manager_can_withdraw_and_restore_a_slot(self):
        self._login(self.manager)
        url = self._slot_url(self.lot, self.slot)

        response = self.client.patch(url, {"status": "OUT_OF_SERVICE"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, "OUT_OF_SERVICE")

        response = self.client.patch(url, {"status": "AVAILABLE"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_occupied_status_is_not_settable_through_the_slot_api(self):
        self._login(self.manager)
        response = self.client.patch(
            self._slot_url(self.lot, self.slot),
            {"status": "OCCUPIED"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    # --- lifecycle ------------------------------------------------------

    def test_delete_and_put_are_not_allowed(self):
        self._login(self.admin)
        url = self._slot_url(self.lot, self.slot)
        self.assertEqual(
            self.client.delete(url).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.put(url, {}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        
        