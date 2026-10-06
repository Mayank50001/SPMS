"""Model tests for the bookings domain (increment 4.1).

API and lifecycle tests arrive with their increments; this file currently
covers only persistence, the snapshot rules and the DB constraints (D39-D41).
"""
import threading
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, connections, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User, Vehicle
from apps.parking.models import BusinessRule, City, ParkingLot, ParkingSlot, Tariff

from apps.bookings.models import Booking

from apps.bookings.services import (
    BookingConflictError, InvalidWindowError, LotNotBookableError,
    MaxDurationExceededError, MinDurationNotMetError, NoTariffError,
    SlotNotFoundError, SlotUnavailableError, WindowInPastError,
    available_slots, blocking_window_q, create_booking,
    expire_stale_holds, hours_between, is_hold_live,
    quote_booking, validate_duration, validate_window,
)


class BookingModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Phase 3 gotcha: a data migration seeds City rows when the test DB is
        # built, so clear them before creating our own.
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        cls.lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
        )
        cls.slot = ParkingSlot.objects.create(
            lot=cls.lot, number="A-01", slot_type=ParkingSlot.SlotType.REGULAR,
        )
        cls.consumer = User.objects.create_user(
            email="consumer@example.com",
            password="Tr0ub4dor&3",
            full_name="Consumer",
        )
        cls.vehicle = Vehicle.objects.create(
            owner=cls.consumer, registration_number="KA01AB1234",
        )

    def make_booking(self, **overrides):
        """Build (do not save) a booking with sensible defaults."""
        now = timezone.now()
        fields = {
            "user": self.consumer,
            "created_by": self.consumer,
            "vehicle": self.vehicle,
            "vehicle_plate": "",
            "slot": self.slot,
            "slot_type": ParkingSlot.SlotType.REGULAR,
            "start_time": now + timedelta(hours=1),
            "end_time": now + timedelta(hours=3),
            "billed_hours": 2,
            "hourly_rate": Decimal("20.00"),
            "base_amount": Decimal("40.00"),
        }
        fields.update(overrides)
        return Booking(**fields)

    # ---- snapshots ---------------------------------------------------------

    def test_plate_snapshot_comes_from_registered_vehicle(self):
        booking = self.make_booking()
        booking.save()
        self.assertEqual(booking.vehicle_plate, "KA01AB1234")

    def test_walkin_free_text_plate_is_canonicalised(self):
        booking = self.make_booking(
            user=None, created_by=None, vehicle=None,
            vehicle_plate="ka01ab1234",
        )
        booking.save()
        self.assertEqual(booking.vehicle_plate, "KA01AB1234")

    def test_base_amount_is_stored_snapshot(self):
        booking = self.make_booking(
            hourly_rate=Decimal("25.50"), billed_hours=3, base_amount=Decimal("76.50"),
        )
        booking.save()
        Booking.objects.filter(pk=booking.pk).update(hourly_rate=Decimal("99.00"))
        booking.refresh_from_db()
        self.assertEqual(booking.base_amount, Decimal("76.50"))

    def test_base_amount_must_be_postive(self):
        booking = self.make_booking(base_amount=Decimal("0.00"))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                booking.save()

    # ---- state -------------------------------------------------------------

    def test_default_status_is_pending_payment(self):
        booking = self.make_booking()
        booking.save()
        self.assertEqual(booking.status, Booking.Status.PENDING_PAYMENT)

    def test_blocking_statuses_are_the_three_active_states(self):
        self.assertEqual(
            set(Booking.BLOCKING_STATUSES),
            {
                Booking.Status.PENDING_PAYMENT,
                Booking.Status.CONFIRMED,
                Booking.Status.IN_PROGRESS,
            },
        )

    # ---- nullable walk-in shape -------------------------------------------

    def test_walkin_allows_null_user_and_vehicle(self):
        booking = self.make_booking(
            user=None, created_by=None, vehicle=None,
            vehicle_plate="KA05XY9999",
        )
        booking.save()
        self.assertIsNone(booking.user)
        self.assertIsNone(booking.vehicle)
        self.assertEqual(booking.vehicle_plate, "KA05XY9999")

    # ---- database constraints ---------------------------------------------

    def test_end_time_must_be_after_start_time(self):
        now = timezone.now()
        booking = self.make_booking(start_time=now, end_time=now)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                booking.save()

    def test_billed_hours_must_be_at_least_one(self):
        booking = self.make_booking(billed_hours=0)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                booking.save()

    def test_blank_plate_is_rejected(self):
        booking = self.make_booking(vehicle=None, vehicle_plate="")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                booking.save()

    # ---- deletion semantics (D39/V6) --------------------------------------

    def test_slot_with_booking_is_protected_from_deletion(self):
        self.make_booking().save()
        with self.assertRaises(ProtectedError):
            self.slot.delete()

    def test_deleting_vehicle_keeps_the_snapshot_plate(self):
        vehicle = Vehicle.objects.create(
            owner=self.consumer, registration_number="DL01AA0001",
        )
        booking = self.make_booking(vehicle=vehicle)
        booking.save()
        vehicle.delete()
        booking.refresh_from_db()
        self.assertIsNone(booking.vehicle)
        self.assertEqual(booking.vehicle_plate, "DL01AA0001")

class BookingServicesTests(TestCase):
    """Pricing, window and conflict helpers (increment 4.2; D42-D45)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        cls.lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
        )
        cls.slot = ParkingSlot.objects.create(
            lot=cls.lot, number="A-01", slot_type=ParkingSlot.SlotType.REGULAR,
        )
        Tariff.objects.create(
            lot=cls.lot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            hourly_rate=Decimal("20.00"),
        )

    def _window(self, start_hours=1, end_hours=3):
        now = timezone.now()
        return now + timedelta(hours=start_hours), now + timedelta(hours=end_hours)

    def _fresh_slot(self):
        # Re-fetch so a test that tweaks the policy cannot leak into the next
        # test through the shared setUpTestData instance.
        return ParkingSlot.objects.get(pk=self.slot.pk)

    def _booking(self, *, start, end, status, hold=None):
        return Booking.objects.create(
            slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=start,
            end_time=end,
            billed_hours=1,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("20.00"),
            status=status,
            hold_expires_at=hold,
            vehicle_plate="KA01AB1234"
        )

    # ---- hours_between -------------------------------------------------

    def test_hours_between_exact_hours(self):
        start, end = self._window(0, 2)
        self.assertEqual(hours_between(start, end), 2)

    def test_hours_between_rounds_any_part_hour_up(self):
        start = timezone.now()
        end = start + timedelta(hours=1, seconds=1)
        self.assertEqual(hours_between(start, end), 2)

    def test_hours_between_one_second_is_one_hour(self):
        start = timezone.now()
        self.assertEqual(hours_between(start, start + timedelta(seconds=1)), 1)

    # ---- window / duration --------------------------------------------

    def test_validate_window_rejects_equal_times(self):
        now = timezone.now()
        with self.assertRaises(InvalidWindowError):
            validate_window(now, now)

    def test_validate_window_rejects_backwards_times(self):
        now = timezone.now()
        with self.assertRaises(InvalidWindowError):
            validate_window(now, now - timedelta(hours=1))

    def test_duration_below_minimum_is_rejected(self):
        slot = self._fresh_slot()
        slot.min_booking_hours = 3
        with self.assertRaises(MinDurationNotMetError):
            validate_duration(slot, 2)

    def test_duration_above_maximum_is_rejected(self):
        slot = self._fresh_slot()
        slot.max_booking_hours = 2
        with self.assertRaises(MaxDurationExceededError):
            validate_duration(slot, 3)

    # ---- quote_booking -------------------------------------------------

    def test_quote_prices_whole_hours(self):
        start, end = self._window(0, 3)
        quote = quote_booking(slot=self.slot, start_time=start, end_time=end)
        self.assertEqual(quote.billed_hours, 3)
        self.assertEqual(quote.hourly_rate, Decimal("20.00"))
        self.assertEqual(quote.base_amount, Decimal("60.00"))

    def test_quote_rounds_up_and_prices_accordingly(self):
        start = timezone.now()
        quote = quote_booking(
            slot=self.slot,
            start_time=start,
            end_time=start + timedelta(hours=2, minutes=30),
        )
        self.assertEqual(quote.billed_hours, 3)
        self.assertEqual(quote.base_amount, Decimal("60.00"))

    def test_quote_without_a_tariff_is_refused(self):
        ev_slot = ParkingSlot.objects.create(
            lot=self.lot, number="E-01", slot_type=ParkingSlot.SlotType.EV,
        )
        start, end = self._window(0, 2)
        with self.assertRaises(NoTariffError):
            quote_booking(slot=ev_slot, start_time=start, end_time=end)

    def test_quote_enforces_the_slot_minimum(self):
        slot = self._fresh_slot()
        slot.min_booking_hours = 3
        start, end = self._window(0, 2)
        with self.assertRaises(MinDurationNotMetError):
            quote_booking(slot=slot, start_time=start, end_time=end)

    def test_quote_enforces_the_slot_maximum(self):
        slot = self._fresh_slot()
        slot.max_booking_hours = 2
        start, end = self._window(0, 3)
        with self.assertRaises(MaxDurationExceededError):
            quote_booking(slot=slot, start_time=start, end_time=end)

    # ---- conflict predicate -------------------------------------------

    def test_confirmed_overlap_blocks(self):
        now = timezone.now()
        self._booking(
            start=now, end=now + timedelta(hours=2),
            status=Booking.Status.CONFIRMED,
        )
        self.assertTrue(
            Booking.objects.filter(
                blocking_window_q(now, now + timedelta(hours=1), now)
            ).exists()
        )

    def test_adjacent_confirmed_window_does_not_block(self):
        now = timezone.now()
        self._booking(
            start=now, end=now + timedelta(hours=1),
            status=Booking.Status.CONFIRMED,
        )
        self.assertFalse(
            Booking.objects.filter(
                blocking_window_q(
                    now + timedelta(hours=1), now + timedelta(hours=2), now
                )
            ).exists()
        )

    def test_live_pending_hold_blocks(self):
        now = timezone.now()
        self._booking(
            start=now, end=now + timedelta(hours=2),
            status=Booking.Status.PENDING_PAYMENT,
            hold=now + timedelta(minutes=5),
        )
        self.assertTrue(
            Booking.objects.filter(
                blocking_window_q(now, now + timedelta(hours=1), now)
            ).exists()
        )

    def test_pending_without_deadline_blocks(self):
        now = timezone.now()
        self._booking(
            start=now, end=now + timedelta(hours=2),
            status=Booking.Status.PENDING_PAYMENT,
            hold=None,
        )
        self.assertTrue(
            Booking.objects.filter(
                blocking_window_q(now, now + timedelta(hours=1), now)
            ).exists()
        )

    def test_lapsed_pending_hold_does_not_block(self):
        now = timezone.now()
        self._booking(
            start=now, end=now + timedelta(hours=2),
            status=Booking.Status.PENDING_PAYMENT,
            hold=now - timedelta(minutes=1),
        )
        self.assertFalse(
            Booking.objects.filter(
                blocking_window_q(now, now + timedelta(hours=1), now)
            ).exists()
        )

    def test_cancelled_booking_does_not_block(self):
        now = timezone.now()
        self._booking(
            start=now, end=now + timedelta(hours=2),
            status=Booking.Status.CANCELLED,
        )
        self.assertFalse(
            Booking.objects.filter(
                blocking_window_q(now, now + timedelta(hours=1), now)
            ).exists()
        )

    # ---- lazy expiry ---------------------------------------------------

    def test_expire_stale_holds_marks_and_timestamps(self):
        now = timezone.now()
        stale = self._booking(
            start=now, end=now + timedelta(hours=2),
            status=Booking.Status.PENDING_PAYMENT,
            hold=now - timedelta(minutes=1),
        )
        self.assertEqual(expire_stale_holds(now=now), 1)
        stale.refresh_from_db()
        self.assertEqual(stale.status, Booking.Status.EXPIRED)
        self.assertGreaterEqual(stale.updated_at, now)

    def test_expire_stale_holds_leaves_live_holds(self):
        now = timezone.now()
        live = self._booking(
            start=now, end=now + timedelta(hours=2),
            status=Booking.Status.PENDING_PAYMENT,
            hold=now + timedelta(minutes=5),
        )
        self.assertEqual(expire_stale_holds(now=now), 0)
        live.refresh_from_db()
        self.assertEqual(live.status, Booking.Status.PENDING_PAYMENT)

    def test_expire_stale_holds_is_scoped_to_a_slot(self):
        now = timezone.now()
        other_slot = ParkingSlot.objects.create(lot=self.lot, number="A-99")
        self._booking(
            start=now, end=now + timedelta(hours=2),
            status=Booking.Status.PENDING_PAYMENT,
            hold=now - timedelta(minutes=1),
        )
        self.assertEqual(expire_stale_holds(slot=other_slot, now=now), 0)

    # ---- is_hold_live --------------------------------------------------

    def test_is_hold_live(self):
        now = timezone.now()
        live = self._booking(
            start=now, end=now + timedelta(hours=2),
            status=Booking.Status.PENDING_PAYMENT,
            hold=now + timedelta(minutes=5),
        )
        lapsed = self._booking(
            start=now + timedelta(hours=5), end=now + timedelta(hours=7),
            status=Booking.Status.PENDING_PAYMENT,
            hold=now - timedelta(minutes=1),
        )
        confirmed = self._booking(
            start=now + timedelta(hours=9), end=now + timedelta(hours=11),
            status=Booking.Status.CONFIRMED,
        )
        self.assertTrue(is_hold_live(live, now))
        self.assertFalse(is_hold_live(lapsed, now))
        self.assertFalse(is_hold_live(confirmed, now))

class AvailabilityQueryTests(TestCase):
    """The time-window availability selector (increment 4.3, D46)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        cls.lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
        )
        cls.slot = ParkingSlot.objects.create(lot=cls.lot, number="A-01")

    def _window(self, start_hours=2, end_hours=4):
        now = timezone.now()
        return now + timedelta(hours=start_hours), now + timedelta(hours=end_hours)

    def _booking(self, *, start, end, status, hold=None):
        return Booking.objects.create(
            slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=start,
            end_time=end,
            billed_hours=1,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("20.00"),
            status=status,
            hold_expires_at=hold,
            vehicle_plate="KA01AB1234",
        )

    def _available_ids(self, start, end):
        return set(
            available_slots(
                lot=self.lot, start_time=start, end_time=end
            ).values_list("id", flat=True)
        )

    def test_free_slot_is_returned(self):
        start, end = self._window()
        self.assertIn(self.slot.id, self._available_ids(start, end))

    def test_confirmed_overlap_hides_the_slot(self):
        start, end = self._window()
        self._booking(start=start, end=end, status=Booking.Status.CONFIRMED)
        self.assertNotIn(self.slot.id, self._available_ids(start, end))

    def test_adjacent_booking_does_not_hide_the_slot(self):
        start, end = self._window()
        # A booking ending exactly when the request begins does not overlap:
        # the interval is half-open (D41).
        self._booking(
            start=end, end=end + timedelta(hours=1),
            status=Booking.Status.CONFIRMED,
        )
        self.assertIn(self.slot.id, self._available_ids(start, end))

    def test_live_pending_hold_hides_the_slot(self):
        start, end = self._window()
        self._booking(
            start=start, end=end, status=Booking.Status.PENDING_PAYMENT,
            hold=timezone.now() + timedelta(minutes=5),
        )
        self.assertNotIn(self.slot.id, self._available_ids(start, end))

    def test_lapsed_hold_does_not_hide_and_is_not_written(self):
        start, end = self._window()
        stale = self._booking(
            start=start, end=end, status=Booking.Status.PENDING_PAYMENT,
            hold=timezone.now() - timedelta(minutes=1),
        )
        self.assertIn(self.slot.id, self._available_ids(start, end))
        # D43: the read must not persist expiry.
        stale.refresh_from_db()
        self.assertEqual(stale.status, Booking.Status.PENDING_PAYMENT)

    def test_cancelled_booking_does_not_hide_the_slot(self):
        start, end = self._window()
        self._booking(start=start, end=end, status=Booking.Status.CANCELLED)
        self.assertIn(self.slot.id, self._available_ids(start, end))

    def test_out_of_service_slot_is_excluded(self):
        self.slot.status = ParkingSlot.Status.OUT_OF_SERVICE
        self.slot.save(update_fields=["status"])
        start, end = self._window()
        self.assertNotIn(self.slot.id, self._available_ids(start, end))

    def test_occupied_slot_is_still_offered(self):
        # D46: OCCUPIED is physical, time-unbounded state owned by Phase 6, so
        # the window query does not exclude it.
        self.slot.status = ParkingSlot.Status.OCCUPIED
        self.slot.save(update_fields=["status"])
        start, end = self._window()
        self.assertIn(self.slot.id, self._available_ids(start, end))

    def test_duration_policy_hides_a_too_long_window(self):
        self.slot.max_booking_hours = 1
        self.slot.save(update_fields=["max_booking_hours"])
        start, end = self._window(2, 4)  # 2 hours > max of 1
        self.assertNotIn(self.slot.id, self._available_ids(start, end))

    def test_duration_policy_hides_a_too_short_window(self):
        self.slot.min_booking_hours = 3
        self.slot.save(update_fields=["min_booking_hours"])
        start, end = self._window(2, 4)  # 2 hours < min of 3
        self.assertNotIn(self.slot.id, self._available_ids(start, end))

    def test_invalid_window_is_refused(self):
        now = timezone.now()
        with self.assertRaises(InvalidWindowError):
            available_slots(lot=self.lot, start_time=now, end_time=now)

    def test_only_the_addressed_lot_is_queried(self):
        other_lot = ParkingLot.objects.create(
            city=City.objects.get(code="BLR"), number=2,
            name="Other", address_line="Other 1",
        )
        other_slot = ParkingSlot.objects.create(lot=other_lot, number="B-01")
        start, end = self._window()
        ids = self._available_ids(start, end)
        self.assertNotIn(other_slot.id, ids)
        self.assertIn(self.slot.id, ids)

class CreateBookingServiceTests(TestCase):
    """``create_booking`` (increment 4.4; D3/D41 and Invariants 1/5/6)."""
    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        cls.lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
        )
        cls.slot = ParkingSlot.objects.create(
            lot=cls.lot, number="A-01", slot_type=ParkingSlot.SlotType.REGULAR,
        )
        Tariff.objects.create(
            lot=cls.lot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            hourly_rate=Decimal("20.00"),
        )
        cls.consumer = User.objects.create_user(
            email="consumer@example.com",
            password="Tr0ub4dor&3",
            full_name="Consumer",
        )
        cls.vehicle = Vehicle.objects.create(
            owner=cls.consumer, registration_number="KA01AB1234",
        )
        # Pre-create the singleton so create's hold read is a plain SELECT.
        BusinessRule.load()

    def _window(self, start_hours=2, end_hours=4):
        now = timezone.now()
        return now + timedelta(hours=start_hours), now + timedelta(hours=end_hours)

    def _create(self, start, end, **overrides):
        params = {
            "slot_id": self.slot.id,
            "start_time": start,
            "end_time": end,
            "user": self.consumer,
            "vehicle": self.vehicle,
        }
        params.update(overrides)
        return create_booking(**params)

    def _existing(self, *args, start, end, status, hold=None):
        return Booking.objects.create(
            slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=start,
            end_time=end,
            billed_hours=1,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("20.00"),
            status=status,
            hold_expires_at=hold,
            vehicle_plate="KA01AB1234",
        )

    # ---- happy path -------------------------------------------------------

    def test_create_stores_snapshot_and_pending_state(self):
        start, end = self._window()
        booking = self._create(start, end)
        self.assertEqual(booking.status, Booking.Status.PENDING_PAYMENT)
        self.assertEqual(booking.user, self.consumer)
        self.assertEqual(booking.created_by, self.consumer)
        self.assertEqual(booking.vehicle_plate, "KA01AB1234")
        self.assertEqual(booking.slot_type, ParkingSlot.SlotType.REGULAR)
        self.assertEqual(booking.billed_hours, 2)
        self.assertEqual(booking.hourly_rate, Decimal("20.00"))
        self.assertEqual(booking.base_amount, Decimal("40.00"))
        self.assertIsNotNone(booking.hold_expires_at)

    def test_hold_uses_business_rule_minutes(self):
        BusinessRule.objects.filter(pk=1).update(hold_minutes=15)
        before = timezone.now()
        start, end = self._window()
        booking = self._create(start, end)
        self.assertGreaterEqual(
            booking.hold_expires_at, before + timedelta(minutes=15)
        )
        self.assertLess(booking.hold_expires_at, before + timedelta(minutes=16))

    # ---- refusals ---------------------------------------------------------

    def test_unknown_slot_is_refused(self):
        start, end = self._window()
        with self.assertRaises(SlotNotFoundError):
            self._create(start, end, slot_id=999999)

    def test_out_of_service_slot_is_refused(self):
        self.slot.status = ParkingSlot.Status.OUT_OF_SERVICE
        self.slot.save(update_fields=["status"])
        start, end = self._window()
        with self.assertRaises(SlotUnavailableError):
            self._create(start, end)

    def test_inactive_lot_is_refused(self):
        self.lot.is_active = False
        self.lot.save(update_fields=["is_active"])
        start, end = self._window()
        with self.assertRaises(LotNotBookableError):
            self._create(start, end)

    def test_past_window_is_refused(self):
        now = timezone.now()
        with self.assertRaises(WindowInPastError):
            self._create(now - timedelta(hours=3), now - timedelta(hours=1))

    def test_overlapping_live_booking_is_refused(self):
        start, end = self._window()
        self._existing(start=start, end=end, status=Booking.Status.CONFIRMED)
        with self.assertRaises(BookingConflictError):
            self._create(start, end)

    def test_adjacent_window_is_allowed(self):
        # The existing booking ends exactly where the new one begins: the
        # half-open interval (D41) means this is NOT a conflict.
        start, end = self._window()
        self._existing(
            start=start - timedelta(hours=2),
            end=start,
            status=Booking.Status.CONFIRMED,
        )
        booking = self._create(start, end)
        self.assertEqual(booking.status, Booking.Status.PENDING_PAYMENT)

    def test_live_pending_hold_blocks(self):
        start, end = self._window()
        self._existing(
            start=start,
            end=end,
            status=Booking.Status.PENDING_PAYMENT,
            hold=timezone.now() + timedelta(minutes=5),
        )
        with self.assertRaises(BookingConflictError):
            self._create(start, end)

    def test_lapsed_hold_is_expired_and_slot_freed(self):
        start, end = self._window()
        stale = self._existing(
            start=start,
            end=end,
            status=Booking.Status.PENDING_PAYMENT,
            hold=timezone.now() - timedelta(minutes=1),
        )
        booking = self._create(start, end)
        self.assertEqual(booking.status, Booking.Status.PENDING_PAYMENT)
        # D43: creation is the only writer of lazy expiry, so the lapsed hold
        # is persisted EXPIRED while holding the lock (Invariant 6).
        stale.refresh_from_db()
        self.assertEqual(stale.status, Booking.Status.EXPIRED)

    def test_duration_policy_is_enforced(self):
        self.slot.max_booking_hours = 1
        self.slot.save(update_fields=["max_booking_hours"])
        start, end = self._window(2, 4)  # 2 hours > max of 1
        with self.assertRaises(MaxDurationExceededError):
            self._create(start, end)

class CreateBookingConcurrencyTests(TransactionTestCase):
    """Two simultaneous creates for one slot: exactly one may win (D3/D41).

    ``TransactionTestCase`` is required: ``TestCase`` wraps each test in a
    transaction, so a second thread could never observe the first's committed
    rows and ``select_for_update`` would not exercise the real race. Each worker
    thread owns its own connection and must close it. PostgreSQL is mandatory
    for this to mean anything (D4): SQLite ignores the lock.
    """

    def setUp(self):
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        self.lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
        )
        self.slot = ParkingSlot.objects.create(
            lot=self.lot, number="A-01", slot_type=ParkingSlot.SlotType.REGULAR,
        )
        Tariff.objects.create(
            lot=self.lot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            hourly_rate=Decimal("20.00"),
        )
        self.consumer = User.objects.create_user(
            email="consumer@example.com",
            password="Tr0ub4dor&3",
            full_name="Consumer",
        )
        self.vehicle = Vehicle.objects.create(
            owner=self.consumer, registration_number="KA01AB1234",
        )
        # Pre-create the singleton so ``load()`` is a read, not a create, in
        # both threads (avoids a get_or_create race on pk=1).
        BusinessRule.load()


    def test_only_one_concurrent_create_wins(self):
        start = timezone.now() + timedelta(hours=2)
        end = start + timedelta(hours=2)

        barrier = threading.Barrier(2)
        results = []
        results_lock = threading.Lock()

        def attempt():
            outcome = "unknown"
            try:
                barrier.wait(timeout=5)
                create_booking(
                    slot_id=self.slot.id,
                    start_time=start,
                    end_time=end,
                    user=self.consumer,
                    vehicle=self.vehicle,
                )
                outcome = "created"
            except BookingConflictError:
                outcome = "conflict"
            except Exception as exc:  # surfaced through the assertion below
                outcome = f"error: {exc!r}"
            finally:
                connections.close_all()
            with results_lock:
                results.append(outcome)

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(sorted(results), ["conflict", "created"])
        self.assertEqual(Booking.objects.filter(slot=self.slot).count(), 1)

class CreateBookingApiTests(TestCase):
    """``POST /api/bookings/`` and the ownership scope of ``GET`` (4.4)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        cls.lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
        )
        cls.slot = ParkingSlot.objects.create(
            lot=cls.lot, number="A-01", slot_type=ParkingSlot.SlotType.REGULAR,
        )
        Tariff.objects.create(
            lot=cls.lot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            hourly_rate=Decimal("20.00"),
        )
        cls.consumer = User.objects.create_user(
            email="consumer@example.com",
            password="Tr0ub4dor&3",
            full_name="Consumer",
        )
        cls.other = User.objects.create_user(
            email="other@example.com",
            password="Tr0ub4dor&3",
            full_name="Other",
        )
        cls.vehicle = Vehicle.objects.create(
            owner=cls.consumer, registration_number="KA01AB1234",
        )
        cls.other_vehicle = Vehicle.objects.create(
            owner=cls.other, registration_number="KA05XY9999",
        )
        BusinessRule.load()

    def setUp(self):
        self.client = APIClient()

    def _window(self, start_hours=2, end_hours=4):
        now = timezone.now()
        return now + timedelta(hours=start_hours), now + timedelta(hours=end_hours)

    def _payload(self, start, end, **overrides):
        payload = {
            "slot": self.slot.id,
            "vehicle": self.vehicle.id,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }
        payload.update(overrides)
        return payload

    def test_anonymous_cannot_create(self):
        start, end = self._window()
        response = self.client.post("/api/bookings/", self._payload(start, end), format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_consumer_creates_booking(self):
        self.client.force_authenticate(self.consumer)
        start, end = self._window()
        response = self.client.post("/api/bookings/", self._payload(start, end), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Booking.Status.PENDING_PAYMENT)
        self.assertEqual(response.data["vehicle_plate"], "KA01AB1234")
        self.assertEqual(response.data["billed_hours"], 2)
        self.assertIsNotNone(response.data["hold_expires_at"])

    def test_consumer_cannot_use_another_consumers_vehicle(self):
        self.client.force_authenticate(self.consumer)
        start, end = self._window()
        response = self.client.post(
            "/api/bookings/", 
            self._payload(start, end, vehicle=self.other_vehicle.id),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vehicle", response.data)

    def test_overlapping_create_returns_conflict(self):
        self.client.force_authenticate(self.consumer)
        start, end = self._window()
        first = self.client.post("/api/bookings/", self._payload(start, end), format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post("/api/bookings/", self._payload(start, end), format="json")
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.data["error"], "BOOKING_CONFLICT")

    def test_invalid_window_is_a_400(self):
        self.client.force_authenticate(self.consumer)
        start, end = self._window()
        response = self.client.post(
            "/api/bookings/", 
            self._payload(start, end, end_time=start.isoformat()),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_past_window_is_a_400(self):
        self.client.force_authenticate(self.consumer)
        now = timezone.now()
        response = self.client.post(
            "/api/bookings/", 
            self._payload(now - timedelta(hours=3), now - timedelta(hours=1)),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "WINDOW_IN_PAST")

    def test_out_of_service_slot_is_a_409(self):
        self.slot.status = ParkingSlot.Status.OUT_OF_SERVICE
        self.slot.save(update_fields=["status"])
        self.client.force_authenticate(self.consumer)
        start, end = self._window()
        response = self.client.post("/api/bookings/", self._payload(start, end), format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"], "SLOT_UNAVAILABLE")

    def test_inactive_lot_is_a_404(self):
        self.lot.is_active = False
        self.lot.save(update_fields=["is_active"])
        self.client.force_authenticate(self.consumer)
        start, end = self._window()
        response = self.client.post("/api/bookings/", self._payload(start, end), format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"], "LOT_NOT_BOOKABLE")

    def test_list_returns_only_the_callers_bookings(self):
        # A booking owned by someone else, created directly.
        now = timezone.now()
        Booking.objects.create(
            user=self.other,
            created_by=self.other,
            vehicle=self.other_vehicle,
            vehicle_plate="",
            slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=10),
            end_time=now + timedelta(hours=12),
            billed_hours=2,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
        )
        self.client.force_authenticate(self.consumer)
        response = self.client.get("/api/bookings/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])