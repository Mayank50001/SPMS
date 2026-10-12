"""Model tests for the parking catalogue (increment 3.1).

Note: ``0002_seed_cities`` is a data migration, so Django applies it when it
builds the test database and the seeded cities (BLR, DEL, ...) are present before
any test runs. Each class therefore clears the table and creates its own data,
so the tests never assert against production seed data or assume an empty table.
"""

from decimal import Decimal
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APIClient
from django.utils import timezone
from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.test_support import page_rows
from .models import City, ParkingLot, ParkingSlot, Tariff, BusinessRule
from .services import MaxRateExceededError, MaxRateBelowTariffError, set_tariff, set_max_hourly_rate, MaxDurationBelowSlotError, set_business_rules

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
        self.assertEqual([lot["code"] for lot in page_rows(response)], ["BLR-001"])

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
        self.assertEqual(len(page_rows(response)), 1)

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
        self.assertEqual(page_rows(response)["code"], "BLR-007")
        self.assertTrue(page_rows(response)["is_active"])

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
        self.assertIn("number", page_rows(response))

    def test_unknown_city_code_is_rejected(self):
        self._login(self.admin)
        payload = {"city_code": "ZZZ", "number": 9, "name": "X", "address_line": "Y"}
        response = self.client.post("/api/parking-lots/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("city_code", page_rows(response))

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
        self.assertIn("manager", page_rows(response))

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
        self.assertEqual([c["code"] for c in page_rows(response)], ["BLR"])

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
        self.assertEqual(page_rows(response)["code"], "MAA")

    def test_duplicate_city_code_is_rejected_case_insensitively(self):
        self._login(self.admin)
        response = self.client.post(
            "/api/cities/", {"code": "blr", "name": "Dup"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", page_rows(response))

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
        Tariff.objects.create(
            lot=cls.lot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            hourly_rate=Decimal("20.00"),
        )
        Tariff.objects.create(
            lot=cls.lot,
            slot_type=ParkingSlot.SlotType.EV,
            hourly_rate=Decimal("30.00"),
        )
        Tariff.objects.create(
            lot=cls.other_lot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            hourly_rate=Decimal("20.00"),
        )

    def setUp(self):
        self.client = APIClient()

    def _login(self, user):
        self.client.force_authenticate(user=user)

    def _slots_url(self, lot):
        return f"/api/parking-lots/{lot.id}/slots/"

    def _slot_url(self, lot, slot):
        return f"/api/parking-lots/{lot.id}/slots/{slot.id}/"

    def _occupancy_url(self, lot, slot):
        return f"/api/parking-lots/{lot.id}/slots/{slot.id}/occupancy/"
    
    def test_anonymous_can_list_slots_of_an_active_lot(self):
        response = self.client.get(self._slots_url(self.lot))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([s["number"] for s in page_rows(response)], ["A-01"])

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
        self.assertEqual([s["number"] for s in page_rows(response)], ["A-01"])

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
        self.assertEqual(page_rows(response)["number"], "A-02")
        self.assertEqual(page_rows(response)["slot_type"], "EV")
        self.assertEqual(page_rows(response)["status"], "AVAILABLE")
        self.assertEqual(page_rows(response)["lot_code"], "BLR-001")

    def test_admin_can_create_slot_and_defaults_apply(self):
        self._login(self.admin)
        response = self.client.post(
            self._slots_url(self.lot), {"number": "A-03"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(page_rows(response)["slot_type"], "REGULAR")
        self.assertEqual(page_rows(response)["status"], "AVAILABLE")

    def test_duplicate_number_in_lot_is_rejected(self):
        self._login(self.admin)
        # Lower-case "a-01" proves canonicalisation feeds the duplicate check.
        response = self.client.post(
            self._slots_url(self.lot), {"number": "a-01"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("number", page_rows(response))

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
        self.assertIn("slot_type", page_rows(response))

    def test_blank_number_is_rejected(self):
        self._login(self.admin)
        response = self.client.post(
            self._slots_url(self.lot), {"number": "   "}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("number", page_rows(response))

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
        self.assertIn("status", page_rows(response))

    def test_anonymous_cannot_change_occupancy(self):
        response = self.client.post(
            self._occupancy_url(self.lot, self.slot),
            {"status": "OCCUPIED"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_consumer_cannot_change_occupancy(self):
        self._login(self.consumer)
        response = self.client.post(
            self._occupancy_url(self.lot, self.slot),
            {"status": "OCCUPIED"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_change_occupancy(self):
        self._login(self.admin)
        response = self.client.post(
            self._occupancy_url(self.lot, self.slot),
            {"status": "OCCUPIED"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassigned_manager_gets_404_on_occupancy(self):
        self._login(self.other_manager)
        response = self.client.post(
            self._occupancy_url(self.lot, self.slot),
            {"status": "OCCUPIED"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_manager_marks_a_slot_occupied_then_available(self):
        self._login(self.manager)
        url = self._occupancy_url(self.lot, self.slot)

        response = self.client.post(url, {"status": "OCCUPIED"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response)["status"], "OCCUPIED")
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, "OCCUPIED")

        response = self.client.post(url, {"status": "AVAILABLE"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, "AVAILABLE")

    def test_out_of_service_slot_cannot_be_marked_occupied(self):
        self.slot.status = ParkingSlot.Status.OUT_OF_SERVICE
        self.slot.save(update_fields=["status"])
        self._login(self.manager)
        response = self.client.post(
            self._occupancy_url(self.lot, self.slot),
            {"status": "OCCUPIED"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(page_rows(response)["error"], "SLOT_NOT_OCCUPIABLE")

    def test_out_of_service_is_not_a_valid_occupancy_status(self):
        self._login(self.manager)
        response = self.client.post(
            self._occupancy_url(self.lot, self.slot),
            {"status": "OUT_OF_SERVICE"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

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

    def test_cannot_create_slot_of_an_unpriced_type(self):
        self._login(self.admin)
        response = self.client.post(
            self._slots_url(self.lot),
            {"number": "A-05", "slot_type" : "LARGE"},
            format = "json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("slot_type", page_rows(response))

class TariffModelTests(TestCase):
    """Model rules for tariffs and the business-rule singleton (increment 3.3)."""

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

    def test_str_includes_lot_code_type_and_rate(self):
        tariff = Tariff.objects.create(
            lot=self.lot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            hourly_rate=Decimal("20.00"),
        )
        self.assertEqual(str(tariff), "BLR-001 - REGULAR: 20.00")

    def test_same_type_in_different_lots_is_allowed(self):
        Tariff.objects.create(lot=self.lot, slot_type="REGULAR", hourly_rate="20.00")
        Tariff.objects.create(
            lot=self.other_lot, slot_type="REGULAR", hourly_rate="25.00"
        )
        self.assertEqual(Tariff.objects.count(), 2)

    def test_type_is_unique_within_a_lot(self):
        Tariff.objects.create(lot=self.lot, slot_type="REGULAR", hourly_rate="20.00")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Tariff.objects.create(
                    lot=self.lot, slot_type="REGULAR", hourly_rate="30.00"
                )

    def test_rate_must_be_positive_at_the_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Tariff.objects.create(
                    lot=self.lot, slot_type="EV", hourly_rate="0.00"
                )

    def test_deleting_a_lot_cascades_to_its_tariffs(self):
        Tariff.objects.create(lot=self.lot, slot_type="REGULAR", hourly_rate="20.00")
        self.lot.delete()
        self.assertEqual(Tariff.objects.count(), 0)

    def test_load_creates_and_reuses_the_singleton(self):
        rule = BusinessRule.load()
        self.assertEqual(rule.pk, 1)
        self.assertEqual(rule.max_hourly_rate, Decimal("100.00"))
        self.assertEqual(BusinessRule.load().pk, 1)
        self.assertEqual(BusinessRule.objects.count(), 1)

    def test_save_always_writes_pk_1(self):
        rule = BusinessRule(max_hourly_rate=Decimal("50.00"))
        rule.pk = 99
        rule.save()
        self.assertEqual(rule.pk, 1)
        self.assertEqual(BusinessRule.objects.count(), 1)

    def test_max_rate_must_be_positive_at_the_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BusinessRule.objects.create(max_hourly_rate=Decimal("0.00"))

class Invariant4ServiceTests(TestCase):
    """Invariant 4 logic lives in services (D35)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        cls.city = City.objects.create(code="BLR", name="Bengaluru")
        cls.lot = ParkingLot.objects.create(
            city=cls.city, number=1, name="MG Road", address_line="MG Road 1"
        )

    def test_tariff_at_the_cap_is_allowed(self):
        set_max_hourly_rate(max_hourly_rate=Decimal("50.00"))
        tariff = set_tariff(
            lot=self.lot, slot_type="REGULAR", hourly_rate=Decimal("50.00")
        )
        self.assertEqual(tariff.hourly_rate, Decimal("50.00"))

    def test_tariff_above_the_cap_is_rejected(self):
        set_max_hourly_rate(max_hourly_rate=Decimal("50.00"))
        with self.assertRaises(MaxRateExceededError):
            set_tariff(
                lot=self.lot, slot_type="REGULAR", hourly_rate=Decimal("50.01")
            )

    def test_update_tariff_within_the_cap_succeeds(self):
        set_max_hourly_rate(max_hourly_rate=Decimal("50.00"))
        tariff = set_tariff(
            lot=self.lot, slot_type="REGULAR", hourly_rate=Decimal("20.00")
        )
        updated = set_tariff(
            lot=self.lot,
            slot_type="REGULAR",
            hourly_rate=Decimal("40.00"),
            instance=tariff,
        )
        self.assertEqual(updated.pk, tariff.pk)
        updated.refresh_from_db()
        self.assertEqual(updated.hourly_rate, Decimal("40.00"))

    def test_lowering_the_cap_below_a_tariff_is_rejected(self):
        set_max_hourly_rate(max_hourly_rate=Decimal("50.00"))
        set_tariff(lot=self.lot, slot_type="REGULAR", hourly_rate=Decimal("40.00"))
        with self.assertRaises(MaxRateBelowTariffError):
            set_max_hourly_rate(max_hourly_rate=Decimal("30.00"))
        # The cap is unchanged, so the invariant still holds at rest.
        self.assertEqual(BusinessRule.load().max_hourly_rate, Decimal("50.00"))

    def test_lowering_the_cap_to_the_highest_tariff_is_allowed(self):
        set_max_hourly_rate(max_hourly_rate=Decimal("50.00"))
        set_tariff(lot=self.lot, slot_type="REGULAR", hourly_rate=Decimal("40.00"))
        rule = set_max_hourly_rate(max_hourly_rate=Decimal("40.00"))
        self.assertEqual(rule.max_hourly_rate, Decimal("40.00"))

class TariffApiTests(TestCase):
    """Tariff and business-rule API surface (increment 3.3)."""

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
            city=cls.city,
            number=1,
            name="MG Road",
            address_line="MG Road 1",
            manager=cls.manager,
        )
        cls.inactive_lot = ParkingLot.objects.create(
            city=cls.city,
            number=2,
            name="Closed",
            address_line="Closed 2",
            manager=cls.manager,
            is_active=False,
        )
        cls.other_lot = ParkingLot.objects.create(
            city=cls.city,
            number=3,
            name="Other",
            address_line="Other 3",
            manager=cls.other_manager,
        )
        cls.tariff = Tariff.objects.create(
            lot=cls.lot, slot_type="REGULAR", hourly_rate=Decimal("20.00")
        )
        set_max_hourly_rate(max_hourly_rate=Decimal("50.00"))

    def setUp(self):
        self.client = APIClient()

    def _login(self, user):
        self.client.force_authenticate(user=user)

    def _tariffs_url(self, lot):
        return f"/api/parking-lots/{lot.id}/tariffs/"

    def _tariff_url(self, lot, tariff):
        return f"/api/parking-lots/{lot.id}/tariffs/{tariff.id}/"

    def test_anonymous_can_list_tariffs_of_an_active_lot(self):
        response = self.client.get(self._tariffs_url(self.lot))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([t["slot_type"] for t in page_rows(response)], ["REGULAR"])

    def test_anonymous_gets_404_for_tariffs_of_an_inactive_lot(self):
        response = self.client.get(self._tariffs_url(self.inactive_lot))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_business_rule_is_publicly_readable(self):
        response = self.client.get("/api/business-rules/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response)["max_hourly_rate"], "50.00")

    def test_anonymous_cannot_create_tariff(self):
        response = self.client.post(self._tariffs_url(self.lot), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_consumer_cannot_create_tariff(self):
        self._login(self.consumer)
        response = self.client.post(self._tariffs_url(self.lot), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassigned_manager_gets_404(self):
        self._login(self.other_manager)
        payload = {"slot_type": "EV", "hourly_rate": "30.00"}
        response = self.client.post(self._tariffs_url(self.lot), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_assigned_manager_can_create_tariff(self):
        self._login(self.manager)
        payload = {"slot_type": "EV", "hourly_rate": "30.00"}
        response = self.client.post(self._tariffs_url(self.lot), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(page_rows(response)["slot_type"], "EV")
        self.assertEqual(page_rows(response)["hourly_rate"], "30.00")
        self.assertEqual(page_rows(response)["lot_code"], "BLR-001")

    def test_tariff_above_the_cap_is_rejected(self):
        self._login(self.manager)
        payload = {"slot_type": "EV", "hourly_rate": "60.00"}
        response = self.client.post(self._tariffs_url(self.lot), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("hourly_rate", page_rows(response))

    def test_zero_or_negative_rate_is_rejected(self):
        self._login(self.manager)
        payload = {"slot_type": "EV", "hourly_rate": "0.00"}
        response = self.client.post(self._tariffs_url(self.lot), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hourly_rate", page_rows(response))

    def test_duplicate_slot_type_in_lot_is_rejected(self):
        self._login(self.manager)
        payload = {"slot_type": "REGULAR", "hourly_rate": "25.00"}
        response = self.client.post(self._tariffs_url(self.lot), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("slot_type", page_rows(response))

    def test_manager_can_update_a_tariff(self):
        self._login(self.manager)
        response = self.client.patch(
            self._tariff_url(self.lot, self.tariff),
            {"hourly_rate": "35.00"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.tariff.refresh_from_db()
        self.assertEqual(self.tariff.hourly_rate, Decimal("35.00"))

    def test_delete_and_put_are_not_allowed_for_tariffs(self):
        self._login(self.admin)
        url = self._tariff_url(self.lot, self.tariff)
        self.assertEqual(
            self.client.delete(url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(
            self.client.put(url, {}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    # --- business rule --------------------------------------------------

    def test_consumer_cannot_change_the_business_rule(self):
        self._login(self.consumer)
        response = self.client.patch(
            "/api/business-rules/", {"max_hourly_rate": "40.00"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_raise_the_cap(self):
        self._login(self.admin)
        response = self.client.patch(
            "/api/business-rules/", {"max_hourly_rate": "80.00"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response)["max_hourly_rate"], "80.00")

    def test_admin_cannot_lower_the_cap_below_a_tariff(self):
        self._login(self.admin)
        response = self.client.patch(
            "/api/business-rules/", {"max_hourly_rate": "10.00"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(page_rows(response)["error"], "MAX_RATE_BELOW_TARIFF")
        
class ManagerScopedLotReadTests(TestCase):
    """Manager-scoped lot catalogue reads (increment 3.4; D37, D38)."""

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
        cls.other_manager = User.objects.create_user(
            email="other@example.com",
            password="Tr0ub4dor&3",
            full_name="Other",
            role=User.Role.MANAGER,
        )
        cls.spare_manager = User.objects.create_user(
            email="spare@example.com",
            password="Tr0ub4dor&3",
            full_name="Spare",
            role=User.Role.MANAGER,
        )
        cls.admin = User.objects.create_user(
            email="admin@example.com",
            password="Tr0ub4dor&3",
            full_name="Admin",
            role=User.Role.ADMIN,
        )

        cls.assigned = ParkingLot.objects.create(
            city=cls.city,
            number=1,
            name="MG Road",
            address_line="MG Road 1",
            manager=cls.manager,
        )
        cls.assigned_closed = ParkingLot.objects.create(
            city=cls.city,
            number=2,
            name="MG Road Depot",
            address_line="Depot 2",
            manager=cls.manager,
            is_active=False,
        )
        cls.unassigned_active = ParkingLot.objects.create(
            city=cls.city, number=3, name="Central", address_line="Central 3"
        )
        cls.other_managers = ParkingLot.objects.create(
            city=cls.city,
            number=4,
            name="Rival",
            address_line="Rival 4",
            manager=cls.other_manager,
        )
        cls.other_managers_closed = ParkingLot.objects.create(
            city=cls.city,
            number=5,
            name="Rival Closed",
            address_line="Rival 5",
            manager=cls.other_manager,
            is_active=False,
        )

    def setUp(self):
        self.client = APIClient()

    def _login(self, user):
        self.client.force_authenticate(user=user)

    def _list_ids(self):
        response = self.client.get("/api/parking-lots/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {lot["id"] for lot in page_rows(response)}

    # --- manager listing: assigned-only (3.4 decision 1a) ---------------

    def test_manager_list_returns_only_assigned_lots(self):
        self._login(self.manager)
        self.assertEqual(
            self._list_ids(), {self.assigned.id, self.assigned_closed.id}
        )

    def test_manager_list_includes_a_deactivated_assigned_lot(self):
        self._login(self.manager)
        self.assertIn(self.assigned_closed.id, self._list_ids())

    def test_manager_list_excludes_unassigned_active_lots(self):
        self._login(self.manager)
        self.assertNotIn(self.unassigned_active.id, self._list_ids())

    def test_manager_list_excludes_another_managers_lots(self):
        self._login(self.manager)
        ids = self._list_ids()
        self.assertNotIn(self.other_managers.id, ids)
        self.assertNotIn(self.other_managers_closed.id, ids)

    def test_manager_with_no_lots_sees_an_empty_list(self):
        self._login(self.spare_manager)
        self.assertEqual(self._list_ids(), set())

    # --- manager listing: filters still apply (3.4 decision 3) ----------

    def test_manager_search_filters_within_assigned_lots(self):
        self._login(self.manager)
        response = self.client.get("/api/parking-lots/?search=Depot")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [lot["id"] for lot in page_rows(response)], [self.assigned_closed.id]
        )

    def test_manager_city_filter_still_applies(self):
        self._login(self.manager)
        response = self.client.get("/api/parking-lots/?city=BLR")
        self.assertEqual(
            {lot["id"] for lot in page_rows(response)},
            {self.assigned.id, self.assigned_closed.id},
        )

    # --- detail: active-or-assigned (3.4 decision 2) --------------------

    def test_manager_can_read_a_deactivated_assigned_lot(self):
        self._login(self.manager)
        response = self.client.get(
            f"/api/parking-lots/{self.assigned_closed.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_manager_can_read_an_unassigned_active_lot(self):
        self._login(self.manager)
        response = self.client.get(
            f"/api/parking-lots/{self.unassigned_active.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_manager_can_read_another_managers_active_lot(self):
        # The detail endpoint remains public; active lots are readable by anyone.
        self._login(self.manager)
        response = self.client.get(f"/api/parking-lots/{self.other_managers.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_manager_gets_404_for_another_managers_deactivated_lot(self):
        self._login(self.manager)
        response = self.client.get(
            f"/api/parking-lots/{self.other_managers_closed.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- everyone else is unchanged (3.4 decision 4) ---------------------

    def test_anonymous_list_is_active_only(self):
        self.assertEqual(
            self._list_ids(),
            {
                self.assigned.id,
                self.unassigned_active.id,
                self.other_managers.id,
            },
        )

    def test_consumer_list_is_active_only(self):
        self._login(self.consumer)
        self.assertEqual(
            self._list_ids(),
            {
                self.assigned.id,
                self.unassigned_active.id,
                self.other_managers.id,
            },
        )

    def test_admin_list_includes_every_lot(self):
        self._login(self.admin)
        self.assertEqual(
            self._list_ids(),
            {
                self.assigned.id,
                self.assigned_closed.id,
                self.unassigned_active.id,
                self.other_managers.id,
                self.other_managers_closed.id,
            },
        )

class SlotDurationPolicyTests(TestCase):
    """Per-slot duration policy + the Administrator's duration cap (D45)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        cls.city = City.objects.create(code="BLR", name="Bengaluru")
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
        cls.lot = ParkingLot.objects.create(
            city=cls.city,
            number=1,
            name="MG Road",
            address_line="MG Road 1",
            manager=cls.manager,
        )
        Tariff.objects.create(
            lot=cls.lot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            hourly_rate=Decimal("20.00"),
        )

    def setUp(self):
        self.client = APIClient()
        # Re-create the singleton per test so a cap change in one test cannot
        # leak into another (TestCase rolls back, but being explicit is clearer).
        BusinessRule.objects.all().delete()

    def _login(self, user):
        self.client.force_authenticate(user=user)

    # --- model ----------------------------------------------------------

    def test_slot_duration_defaults(self):
        slot = ParkingSlot.objects.create(lot=self.lot, number="A-01")
        self.assertEqual(slot.min_booking_hours, 1)
        self.assertEqual(slot.max_booking_hours, 24)

    def test_min_above_max_is_rejected_at_the_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ParkingSlot.objects.create(
                    lot=self.lot,
                    number="A-02",
                    min_booking_hours=5,
                    max_booking_hours=2,
                )

    def test_business_rule_duration_cap_default(self):
        self.assertEqual(BusinessRule.load().max_booking_hours, 72)

    # --- service: lowering the cap --------------------------------------

    def test_lowering_cap_below_a_slot_max_is_rejected(self):
        ParkingSlot.objects.create(
            lot=self.lot, number="A-04", max_booking_hours=48
        )
        with self.assertRaises(MaxDurationBelowSlotError):
            set_business_rules(max_booking_hours=24)
        self.assertEqual(BusinessRule.load().max_booking_hours, 72)

    def test_lowering_cap_to_the_highest_slot_max_is_allowed(self):
        ParkingSlot.objects.create(
            lot=self.lot, number="A-05", max_booking_hours=48
        )
        rule = set_business_rules(max_booking_hours=48)
        self.assertEqual(rule.max_booking_hours, 48)

    # --- API: slot duration ---------------------------------------------

    def test_manager_can_set_slot_duration_policy(self):
        self._login(self.manager)
        response = self.client.post(
            f"/api/parking-lots/{self.lot.id}/slots/",
            {"number": "B-01", "min_booking_hours": 2, "max_booking_hours": 4},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(page_rows(response)["min_booking_hours"], 2)
        self.assertEqual(page_rows(response)["max_booking_hours"], 4)

    def test_slot_max_above_the_cap_is_a_409(self):
        set_business_rules(max_booking_hours=24)
        self._login(self.manager)
        response = self.client.post(
            f"/api/parking-lots/{self.lot.id}/slots/",
            {"number": "B-02", "max_booking_hours": 30},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(page_rows(response)["error"], "MAX_DURATION_ABOVE_CAP")

    def test_patching_slot_max_above_the_cap_is_a_409(self):
        slot = ParkingSlot.objects.create(lot=self.lot, number="B-03")
        set_business_rules(max_booking_hours=24)
        self._login(self.manager)
        response = self.client.patch(
            f"/api/parking-lots/{self.lot.id}/slots/{slot.id}/",
            {"max_booking_hours": 30},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(page_rows(response)["error"], "MAX_DURATION_ABOVE_CAP")

    def test_min_greater_than_max_is_a_400(self):
        self._login(self.manager)
        response = self.client.post(
            f"/api/parking-lots/{self.lot.id}/slots/",
            {"number": "B-04", "min_booking_hours": 5, "max_booking_hours": 2},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("max_booking_hours", page_rows(response))

    def test_public_can_read_slot_duration_fields(self):
        ParkingSlot.objects.create(lot=self.lot, number="B-06")
        response = self.client.get(f"/api/parking-lots/{self.lot.id}/slots/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response)[0]["min_booking_hours"], 1)
        self.assertEqual(page_rows(response)[0]["max_booking_hours"], 24)

    # --- API: the Administrator's duration cap --------------------------

    def test_business_rule_exposes_the_duration_cap(self):
        response = self.client.get("/api/business-rules/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response)["max_booking_hours"], 72)

    def test_admin_can_raise_the_duration_cap(self):
        self._login(self.admin)
        response = self.client.patch(
            "/api/business-rules/", {"max_booking_hours": 96}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response)["max_booking_hours"], 96)

    def test_admin_cannot_lower_duration_cap_below_a_slot(self):
        ParkingSlot.objects.create(
            lot=self.lot, number="B-05", max_booking_hours=48
        )
        self._login(self.admin)
        response = self.client.patch(
            "/api/business-rules/", {"max_booking_hours": 12}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(page_rows(response)["error"], "MAX_DURATION_BELOW_SLOT")

    def test_empty_business_rule_patch_is_rejected(self):
        self._login(self.admin)
        response = self.client.patch("/api/business-rules/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

class AvailabilityApiTests(TestCase):
    """The derived availability endpoint (increment 4.3, D46)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        cls.city = City.objects.create(code="BLR", name="Bengaluru")
        cls.lot = ParkingLot.objects.create(
            city=cls.city, number=1, name="MG Road", address_line="MG Road 1"
        )
        cls.manager = User.objects.create_user(
            email="manager@example.com",
            password="Tr0ub4dor&3",
            full_name="Manager",
            role=User.Role.MANAGER,
        )
        cls.inactive = ParkingLot.objects.create(
            city=cls.city, number=2, name="Closed", address_line="Closed 2",
            is_active=False, manager=cls.manager,
        )
        cls.slot = ParkingSlot.objects.create(lot=cls.lot, number="A-01")
        ParkingSlot.objects.create(
            lot=cls.lot, number="A-02",
            status=ParkingSlot.Status.OUT_OF_SERVICE,
        )
        Tariff.objects.create(
            lot=cls.lot, slot_type=ParkingSlot.SlotType.REGULAR,
            hourly_rate=Decimal("20.00"),
        )

    def setUp(self):
        self.client = APIClient()

    def _window(self):
        start = timezone.now() + timedelta(hours=2)
        return start, start + timedelta(hours=2)

    def _url(self, lot=None):
        return f"/api/parking-lots/{(lot or self.lot).id}/availability/"

    def test_anonymous_can_query_availability(self):
        start, end = self._window()
        response = self.client.get(
            self._url(), {"start": start.isoformat(), "end": end.isoformat()}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([s["number"] for s in page_rows(response)], ["A-01"])

    def test_missing_window_params_are_rejected(self):
        self.assertEqual(
            self.client.get(self._url()).status_code, status.HTTP_400_BAD_REQUEST
        )
        response = self.client.get(
            self._url(), {"start": timezone.now().isoformat()}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_backwards_window_is_invalid_window(self):
        start, _ = self._window()
        response = self.client.get(
            self._url(), {"start": start.isoformat(), "end": start.isoformat()}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(page_rows(response)["error"], "INVALID_WINDOW")

    def test_out_of_service_slot_is_absent(self):
        start, end = self._window()
        response = self.client.get(
            self._url(), {"start": start.isoformat(), "end": end.isoformat()}
        )
        self.assertNotIn("A-02", [s["number"] for s in page_rows(response)])

    def test_confirmed_overlap_is_absent(self):
        start, end = self._window()
        Booking.objects.create(
            slot=self.slot, slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=start, end_time=end, billed_hours=2,
            hourly_rate=Decimal("20.00"), base_amount=Decimal("40.00"),
            status=Booking.Status.CONFIRMED, vehicle_plate="KA01AB1234",
        )
        response = self.client.get(
            self._url(), {"start": start.isoformat(), "end": end.isoformat()}
        )
        self.assertEqual(page_rows(response), [])

    def test_inactive_lot_is_404_for_anonymous(self):
        start, end = self._window()
        response = self.client.get(
            self._url(self.inactive),
            {"start": start.isoformat(), "end": end.isoformat()},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_manager_can_query_an_inactive_assigned_lot(self):
        self.client.force_authenticate(user=self.manager)
        start, end = self._window()
        response = self.client.get(
            self._url(self.inactive),
            {"start": start.isoformat(), "end": end.isoformat()},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response), [])

class HoldMinutesRuleTests(TestCase):
    """D6/§19: the hold length is part of the BusinessRule singleton (4.4)."""
    def setUp(self):
        BusinessRule.objects.all().delete()
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="Tr0ub4dor&3",
            full_name="Admin",
            role=User.Role.ADMIN,
        )
        self.client = APIClient()

    def test_default_is_five_minutes(self):
        self.assertEqual(BusinessRule.load().hold_minutes, 5)

    def test_admin_can_update_hold_minutes(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            "/api/business-rules/", {"hold_minutes": 10}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(page_rows(response)["hold_minutes"], 10)
        self.assertEqual(BusinessRule.load().hold_minutes, 10)

class CancellationCutoffRuleTests(TestCase):
    """§19/D53: the refund cutoff is part of the BusinessRule singleton (4.7)."""

    def setUp(self):
        BusinessRule.objects.all().delete()
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="Tr0ub4dor&3",
            full_name="Admin",
            role=User.Role.ADMIN,
        )
        self.client = APIClient()

    def test_default_is_thirty_minutes(self):
        self.assertEqual(BusinessRule.load().cancellation_cutoff_minutes, 30)

    def test_rule_read_exposes_the_cutoff(self):
        response = self.client.get("/api/business-rules/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(page_rows(response)["cancellation_cutoff_minutes"], 30)

    def test_admin_can_update_cutoff(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            "/api/business-rules/", {"cancellation_cutoff_minutes": 60}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(page_rows(response)["cancellation_cutoff_minutes"], 60)
        self.assertEqual(BusinessRule.load().cancellation_cutoff_minutes, 60)

    def test_non_admin_cannot_update_cutoff(self):
        consumer = User.objects.create_user(
            email="consumer@example.com",
            password="Tr0ub4dor&3",
            full_name="Consumer",
        )
        self.client.force_authenticate(consumer)
        response = self.client.patch(
            "/api/business-rules/", {"cancellation_cutoff_minutes": 60}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(BusinessRule.load().cancellation_cutoff_minutes, 30)

class OverstayRuleTests(TestCase):
    """D70/§19: the overstay multiplier and grace window are BusinessRules."""

    def setUp(self):
        BusinessRule.objects.all().delete()
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="Tr0ub4dor&3",
            full_name="Admin",
            role=User.Role.ADMIN,
        )
        self.client = APIClient()

    def test_defaults(self):
        rule = BusinessRule.load()
        self.assertEqual(rule.overstay_multiplier, Decimal("1.50"))
        self.assertEqual(rule.overstay_grace_minutes, 15)

    def test_rule_read_exposes_the_overstay_settings(self):
        response = self.client.get("/api/business-rules/")
        self.assertEqual(response.status_code, 200)
        row = page_rows(response)
        self.assertEqual(row["overstay_multiplier"], "1.50")
        self.assertEqual(row["overstay_grace_minutes"], 15)

    def test_admin_can_change_the_overstay_rules(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            "/api/business-rules/",
            {"overstay_multiplier": "2.00", "overstay_grace_minutes": 30},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        rule = BusinessRule.load()
        self.assertEqual(rule.overstay_multiplier, Decimal("2.00"))
        self.assertEqual(rule.overstay_grace_minutes, 30)

    def test_a_multiplier_below_one_is_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            "/api/business-rules/", {"overstay_multiplier": "0.50"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("overstay_multiplier", page_rows(response))