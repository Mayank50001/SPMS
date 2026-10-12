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
from apps.test_support import page_rows

from apps.bookings.references import (
    REFERENCE_ALPHABET, REFERENCE_LENGTH, generate_reference,
)

from apps.bookings.services import (
    BookingConflictError, BookingNotCancellableError, BookingNotConfirmableError,
    BookingNotExtendableError, BookingNotFoundError, InvalidExtensionError,
    InvalidWindowError, LotNotBookableError,
    MaxDurationExceededError, MinDurationNotMetError, NoTariffError,
    SlotNotFoundError, SlotUnavailableError, WindowInPastError,
    available_slots, blocking_window_q, cancel_booking, confirm_booking,
    create_booking, effective_status, expire_stale_holds, extend_booking,
    hours_between, is_hold_live, quote_booking, quote_extension, refund_due_for,
    validate_duration, validate_window, filter_bookings
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

class EffectiveStatusTests(TestCase):
    """Lazy-hold presentation: a lapsed hold reads as EXPIRED (increment 4.5, D50)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        cls.lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
        )
        cls.slot = ParkingSlot.objects.create(lot=cls.lot, number="A-01")

    def _booking(self, *, status, hold="unset"):
        now = timezone.now()
        if hold == "unset":
            hold = None
        return Booking.objects.create(
            slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=4),
            billed_hours=2,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
            status=status,
            hold_expires_at=hold,
            vehicle_plate="KA01AB1234",
        )

    def test_live_pending_hold_reads_as_pending(self):
        now = timezone.now()
        booking = self._booking(
            status=Booking.Status.PENDING_PAYMENT, hold=now + timedelta(minutes=5)
        )
        self.assertEqual(effective_status(booking, now), Booking.Status.PENDING_PAYMENT)

    def test_lapsed_pending_hold_reads_as_expired(self):
        now = timezone.now()
        booking = self._booking(
            status=Booking.Status.PENDING_PAYMENT, hold=now - timedelta(seconds=1)
        )
        self.assertEqual(effective_status(booking, now), Booking.Status.EXPIRED)

    def test_pending_without_deadline_never_expires(self):
        now = timezone.now()
        booking = self._booking(status=Booking.Status.PENDING_PAYMENT, hold=None)
        self.assertEqual(effective_status(booking, now), Booking.Status.PENDING_PAYMENT)

    def test_non_pending_status_is_returned_unchanged(self):
        now = timezone.now()
        booking = self._booking(
            status=Booking.Status.CONFIRMED, hold=now - timedelta(hours=1)
        )
        self.assertEqual(effective_status(booking, now), Booking.Status.CONFIRMED)

    def test_effective_status_does_not_persist(self):
        # D43/4.5-Q4: reading the effective state must not write. The stored
        # status stays PENDING_PAYMENT even though a reader sees EXPIRED.
        now = timezone.now()
        booking = self._booking(
            status=Booking.Status.PENDING_PAYMENT, hold=now - timedelta(seconds=1)
        )
        self.assertEqual(effective_status(booking, now), Booking.Status.EXPIRED)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING_PAYMENT)

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

    def test_occupied_slot_is_hidden_for_a_started_window(self):
        # D68: occupied is a *now*-fact, so a window that has already begun
        # cannot use the bay.
        self.slot.status = ParkingSlot.Status.OCCUPIED
        self.slot.save(update_fields=["status"])
        now = timezone.now()
        ids = self._available_ids(
            now - timedelta(minutes=30), now + timedelta(hours=1)
        )
        self.assertNotIn(self.slot.id, ids)

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

    def test_occupied_slot_is_refused_for_a_started_window(self):
        self.slot.status = ParkingSlot.Status.OCCUPIED
        self.slot.save(update_fields=["status"])
        now = timezone.now()
        with self.assertRaises(SlotUnavailableError):
            self._create(now - timedelta(minutes=30), now + timedelta(hours=1))

    def test_occupied_slot_is_bookable_for_a_future_window(self):
        # D68: a momentarily-full lot must still accept tomorrow's booking.
        self.slot.status = ParkingSlot.Status.OCCUPIED
        self.slot.save(update_fields=["status"])
        start, end = self._window()  # now + 2h .. now + 4h
        booking = self._create(start, end)
        self.assertEqual(booking.status, Booking.Status.PENDING_PAYMENT)

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

    def test_manager_cannot_create(self):
        manager = User.objects.create_user(
            email="manager@example.com",
            password="Tr0ub4dor&3",
            full_name="Manager",
            role=User.Role.MANAGER,
        )
        self.client.force_authenticate(manager)
        start, end = self._window()
        response = self.client.post("/api/bookings/", self._payload(start, end), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
    def test_consumer_creates_booking(self):
        self.client.force_authenticate(self.consumer)
        start, end = self._window()
        response = self.client.post("/api/bookings/", self._payload(start, end), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(page_rows(response)["status"], Booking.Status.PENDING_PAYMENT)
        self.assertEqual(page_rows(response)["vehicle_plate"], "KA01AB1234")
        self.assertEqual(page_rows(response)["billed_hours"], 2)
        self.assertIsNotNone(page_rows(response)["hold_expires_at"])

    def test_consumer_cannot_use_another_consumers_vehicle(self):
        self.client.force_authenticate(self.consumer)
        start, end = self._window()
        response = self.client.post(
            "/api/bookings/", 
            self._payload(start, end, vehicle=self.other_vehicle.id),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vehicle", page_rows(response))

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
        self.assertEqual(page_rows(response)["error"], "WINDOW_IN_PAST")

    def test_out_of_service_slot_is_a_409(self):
        self.slot.status = ParkingSlot.Status.OUT_OF_SERVICE
        self.slot.save(update_fields=["status"])
        self.client.force_authenticate(self.consumer)
        start, end = self._window()
        response = self.client.post("/api/bookings/", self._payload(start, end), format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(page_rows(response)["error"], "SLOT_UNAVAILABLE")

    def test_inactive_lot_is_a_404(self):
        self.lot.is_active = False
        self.lot.save(update_fields=["is_active"])
        self.client.force_authenticate(self.consumer)
        start, end = self._window()
        response = self.client.post("/api/bookings/", self._payload(start, end), format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(page_rows(response)["error"], "LOT_NOT_BOOKABLE")

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
        self.assertEqual(page_rows(response), [])

    # ---- effective status (increment 4.5, D50) ----------------------------

    def test_create_response_reports_a_live_effective_status(self):
        self.client.force_authenticate(self.consumer)
        start, end = self._window()
        response = self.client.post("/api/bookings/", self._payload(start, end), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(page_rows(response)["status"], Booking.Status.PENDING_PAYMENT)
        self.assertEqual(page_rows(response)["effective_status"], Booking.Status.PENDING_PAYMENT)

    def test_list_reports_a_lapsed_hold_as_expired_without_persisting(self):
        now = timezone.now()
        booking = Booking.objects.create(
            user=self.consumer,
            created_by=self.consumer,
            vehicle=self.vehicle,
            vehicle_plate="",
            slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=10),
            end_time=now + timedelta(hours=12),
            billed_hours=2,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
            status=Booking.Status.PENDING_PAYMENT,
            hold_expires_at=now - timedelta(minutes=1),
        )
        self.client.force_authenticate(self.consumer)
        response = self.client.get("/api/bookings/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(page_rows(response)), 1)
        # The reader sees EXPIRED; the row is untouched (D43, 4.5-Q4).
        self.assertEqual(page_rows(response)[0]["effective_status"], Booking.Status.EXPIRED)
        self.assertEqual(page_rows(response)[0]["status"], Booking.Status.PENDING_PAYMENT)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING_PAYMENT)

    # ---- public reference (increment 4.6, D52) ----------------------------

    def test_create_response_includes_a_generated_reference(self):
        self.client.force_authenticate(self.consumer)
        start, end = self._window()
        response = self.client.post("/api/bookings/", self._payload(start, end), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        reference = page_rows(response)["reference"]
        self.assertEqual(len(reference), REFERENCE_LENGTH)
        self.assertTrue(all(ch in REFERENCE_ALPHABET for ch in reference))

    def test_client_cannot_choose_the_reference(self):
        # The reference is server-generated; a client-supplied value is ignored
        # (it is not a field of BookingCreateSerializer).
        self.client.force_authenticate(self.consumer)
        start, end = self._window()
        response = self.client.post(
            "/api/bookings/",
            self._payload(start, end, reference="MINE123456"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(page_rows(response)["reference"], "MINE123456")

class ReferenceTests(TestCase):
    """The public reference code (increment 4.6, D52)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        cls.lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
        )
        cls.slot = ParkingSlot.objects.create(lot=cls.lot, number="A-01")

    def _booking(self, offset_hours=2):
        now = timezone.now()
        return Booking.objects.create(
            slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=offset_hours),
            end_time=now + timedelta(hours=offset_hours + 2),
            billed_hours=2,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
            vehicle_plate="KA01AB1234",
        )

    def test_generate_reference_shape(self):
        code = generate_reference()
        self.assertEqual(len(code), REFERENCE_LENGTH)
        self.assertTrue(all(ch in REFERENCE_ALPHABET for ch in code))

    def test_booking_gets_a_reference_on_save(self):
        booking = self._booking()
        self.assertEqual(len(booking.reference), REFERENCE_LENGTH)
        self.assertTrue(all(ch in REFERENCE_ALPHABET for ch in booking.reference))

    def test_references_are_unique(self):
        codes = {self._booking(offset_hours=h).reference for h in (2, 6, 10, 14)}
        self.assertEqual(len(codes), 4)

    def test_reference_is_not_editable(self):
        # D52: generated server-side; ``editable=False`` keeps it out of forms
        # and write serializers (the read serializer still reports it).
        self.assertFalse(Booking._meta.get_field("reference").editable)

class ConfirmBookingServiceTests(TestCase):
    """The confirmation seam ``confirm_booking`` (increment 4.6, D51)."""

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
        BusinessRule.load()

    def _window(self, start_hours=2, end_hours=4):
        now = timezone.now()
        return now + timedelta(hours=start_hours), now + timedelta(hours=end_hours)

    def _pending(self, *, start_hours=2, end_hours=4, hold_minutes=5):
        start, end = self._window(start_hours, end_hours)
        booking = create_booking(
            slot_id=self.slot.id,
            start_time=start,
            end_time=end,
            user=self.consumer,
            vehicle=self.vehicle,
        )
        if hold_minutes is not None:
            Booking.objects.filter(pk=booking.pk).update(
                hold_expires_at=timezone.now() + timedelta(minutes=hold_minutes)
            )
            booking.refresh_from_db()
        return booking

    def test_confirm_live_pending_sets_confirmed_and_clears_hold(self):
        booking = self._pending()
        confirmed = confirm_booking(booking_id=booking.pk)
        self.assertEqual(confirmed.status, Booking.Status.CONFIRMED)
        self.assertIsNone(confirmed.hold_expires_at)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertIsNone(booking.hold_expires_at)

    def test_successful_confirmation_sweeps_other_stale_holds(self):
        # Reusing the one expiry sweep (D43) inside the lock means a successful
        # confirmation also retires any other lapsed hold on the slot, and this
        # time it commits.
        now = timezone.now()
        stale = Booking.objects.create(
            slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=10),
            end_time=now + timedelta(hours=12),
            billed_hours=2,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
            status=Booking.Status.PENDING_PAYMENT,
            hold_expires_at=now - timedelta(minutes=1),
            vehicle_plate="KA05XY9999",
        )
        live = self._pending()
        confirm_booking(booking_id=live.pk)
        stale.refresh_from_db()
        self.assertEqual(stale.status, Booking.Status.EXPIRED)

    def test_repeat_confirmation_is_idempotent(self):
        # Payment gateways retry callbacks; a second confirmation must not fail.
        booking = self._pending()
        first = confirm_booking(booking_id=booking.pk)
        second = confirm_booking(booking_id=booking.pk)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(second.status, Booking.Status.CONFIRMED)

    def test_lapsed_hold_is_refused(self):
        booking = self._pending(hold_minutes=-1)
        with self.assertRaises(BookingNotConfirmableError) as caught:
            confirm_booking(booking_id=booking.pk)
        self.assertEqual(caught.exception.code, "BOOKING_NOT_CONFIRMABLE")
        # The attempt is atomic: a refusal rolls the in-lock sweep back, leaving
        # the stored row as-is. That is harmless -- a lapsed hold no longer
        # blocks (D41) and reads already report it as EXPIRED (D50) -- and the
        # next write sweeps it.
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING_PAYMENT)
        self.assertEqual(effective_status(booking), Booking.Status.EXPIRED)

    def test_cancelled_booking_is_refused(self):
        booking = self._pending()
        Booking.objects.filter(pk=booking.pk).update(
            status=Booking.Status.CANCELLED
        )
        with self.assertRaises(BookingNotConfirmableError):
            confirm_booking(booking_id=booking.pk)

    def test_unknown_booking_is_refused(self):
        with self.assertRaises(BookingNotFoundError):
            confirm_booking(booking_id=999999)

    def test_confirmation_refuses_when_the_window_was_taken(self):
        # Force the race the slot lock guards: booking A is still pending/live,
        # but another confirmed booking already overlaps its window (created
        # directly, bypassing the service). Confirmation must refuse rather than
        # create a second confirmed overlap (Invariant 1).
        booking = self._pending(hold_minutes=30)
        now = timezone.now()
        Booking.objects.create(
            slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=4),
            billed_hours=2,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
            status=Booking.Status.CONFIRMED,
            vehicle_plate="KA05XY9999",
        )
        with self.assertRaises(BookingConflictError):
            confirm_booking(booking_id=booking.pk)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING_PAYMENT)

class RefundDueTests(TestCase):
    """The §19 refund rule ``refund_due_for`` (increment 4.7, D53)."""

    def _booking(self, *, status, start_delta):
        now = timezone.now()
        return Booking(
            status=status,
            base_amount=Decimal("40.00"),
            start_time=now + start_delta,
        )

    def test_pending_booking_owes_no_refund(self):
        now = timezone.now()
        booking = self._booking(
            status=Booking.Status.PENDING_PAYMENT, start_delta=timedelta(hours=2)
        )
        self.assertEqual(
            refund_due_for(booking, now=now, cutoff_minutes=30), Decimal("0.00")
        )

    def test_confirmed_before_the_cutoff_is_fully_refunded(self):
        now = timezone.now()
        booking = self._booking(
            status=Booking.Status.CONFIRMED, start_delta=timedelta(hours=2)
        )
        self.assertEqual(
            refund_due_for(booking, now=now, cutoff_minutes=30), Decimal("40.00")
        )

    def test_confirmed_exactly_at_the_cutoff_is_refunded(self):
        # "at least 30 minutes before" includes the boundary: the same ``now``
        # is used for both the booking and the rule, so this is deterministic.
        now = timezone.now()
        booking = Booking(
            status=Booking.Status.CONFIRMED,
            base_amount=Decimal("40.00"),
            start_time=now + timedelta(minutes=30),
        )
        self.assertEqual(
            refund_due_for(booking, now=now, cutoff_minutes=30), Decimal("40.00")
        )

    def test_confirmed_inside_the_cutoff_is_not_refunded(self):
        now = timezone.now()
        booking = Booking(
            status=Booking.Status.CONFIRMED,
            base_amount=Decimal("40.00"),
            start_time=now + timedelta(minutes=29),
        )
        self.assertEqual(
            refund_due_for(booking, now=now, cutoff_minutes=30), Decimal("0.00")
        )

    def test_confirmed_after_start_is_not_refunded(self):
        now = timezone.now()
        booking = Booking(
            status=Booking.Status.CONFIRMED,
            base_amount=Decimal("40.00"),
            start_time=now - timedelta(minutes=5),
        )
        self.assertEqual(
            refund_due_for(booking, now=now, cutoff_minutes=30), Decimal("0.00")
        )

class CancelBookingServiceTests(TestCase):
    """``cancel_booking`` (increment 4.7, D53 and §19)."""

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

    def _window(self, start_hours=2, end_hours=4):
        now = timezone.now()
        return now + timedelta(hours=start_hours), now + timedelta(hours=end_hours)

    def _create(self, *, owner=None, vehicle=None, start_hours=2, end_hours=4):
        owner = owner or self.consumer
        vehicle = vehicle or self.vehicle
        start, end = self._window(start_hours, end_hours)
        return create_booking(
            slot_id=self.slot.id,
            start_time=start,
            end_time=end,
            user=owner,
            vehicle=vehicle,
        )

    def test_cancel_pending_sets_cancelled_and_frees_the_slot(self):
        booking = self._create()
        cancelled = cancel_booking(booking_id=booking.pk, user=self.consumer)
        self.assertEqual(cancelled.status, Booking.Status.CANCELLED)
        self.assertIsNotNone(cancelled.cancelled_at)
        self.assertEqual(cancelled.cancelled_by, self.consumer)
        self.assertEqual(cancelled.refund_due_amount, Decimal("0.00"))
        # The slot is usable again: cancellation removes the blocking booking.
        again = self._create()
        self.assertEqual(again.status, Booking.Status.PENDING_PAYMENT)

    def test_cancel_lapsed_pending_is_allowed_with_no_refund(self):
        # 4.5 reported a lapsed hold as EXPIRED; 4.7 owns the actual release, so
        # the owner may still cancel it and free the slot. No payment, no refund.
        booking = self._create()
        Booking.objects.filter(pk=booking.pk).update(
            hold_expires_at=timezone.now() - timedelta(minutes=1)
        )
        cancelled = cancel_booking(booking_id=booking.pk, user=self.consumer)
        self.assertEqual(cancelled.status, Booking.Status.CANCELLED)
        self.assertEqual(cancelled.refund_due_amount, Decimal("0.00"))

    def test_cancel_confirmed_before_cutoff_refunds_the_base_amount(self):
        booking = self._create()
        confirm_booking(booking_id=booking.pk)
        cancelled = cancel_booking(booking_id=booking.pk, user=self.consumer)
        self.assertEqual(cancelled.status, Booking.Status.CANCELLED)
        self.assertEqual(cancelled.refund_due_amount, Decimal("40.00"))

    def test_cancel_confirmed_inside_cutoff_is_not_refunded(self):
        booking = self._create()
        confirm_booking(booking_id=booking.pk)
        Booking.objects.filter(pk=booking.pk).update(
            start_time=timezone.now() + timedelta(minutes=10)
        )
        cancelled = cancel_booking(booking_id=booking.pk, user=self.consumer)
        self.assertEqual(cancelled.refund_due_amount, Decimal("0.00"))

    def test_cutoff_comes_from_the_business_rule(self):
        BusinessRule.objects.filter(pk=1).update(cancellation_cutoff_minutes=240)
        booking = self._create()  # 2 hours away
        confirm_booking(booking_id=booking.pk)
        cancelled = cancel_booking(booking_id=booking.pk, user=self.consumer)
        self.assertEqual(cancelled.refund_due_amount, Decimal("0.00"))

    def test_in_progress_booking_is_refused(self):
        booking = self._create()
        Booking.objects.filter(pk=booking.pk).update(
            status=Booking.Status.IN_PROGRESS
        )
        with self.assertRaises(BookingNotCancellableError) as caught:
            cancel_booking(booking_id=booking.pk, user=self.consumer)
        self.assertEqual(caught.exception.code, "BOOKING_NOT_CANCELLABLE")

    def test_completed_booking_is_refused(self):
        booking = self._create()
        Booking.objects.filter(pk=booking.pk).update(status=Booking.Status.COMPLETED)
        with self.assertRaises(BookingNotCancellableError):
            cancel_booking(booking_id=booking.pk, user=self.consumer)

    def test_repeat_cancel_is_idempotent(self):
        booking = self._create()
        first = cancel_booking(booking_id=booking.pk, user=self.consumer)
        second = cancel_booking(booking_id=booking.pk, user=self.consumer)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(second.status, Booking.Status.CANCELLED)
        self.assertEqual(second.cancelled_at, first.cancelled_at)

    def test_another_consumers_booking_is_not_found(self):
        booking = self._create(owner=self.other, vehicle=self.other_vehicle)
        with self.assertRaises(BookingNotFoundError):
            cancel_booking(booking_id=booking.pk, user=self.consumer)

    def test_unknown_booking_is_not_found(self):
        with self.assertRaises(BookingNotFoundError):
            cancel_booking(booking_id=999999, user=self.consumer)

class CancelBookingApiTests(TestCase):
    """``POST /api/bookings/{id}/cancel/`` (increment 4.7, D53)."""

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

    def _create(self, *, owner=None, vehicle=None, start_hours=2, end_hours=4):
        owner = owner or self.consumer
        vehicle = vehicle or self.vehicle
        now = timezone.now()
        return create_booking(
            slot_id=self.slot.id,
            start_time=now + timedelta(hours=start_hours),
            end_time=now + timedelta(hours=end_hours),
            user=owner,
            vehicle=vehicle,
        )

    def _url(self, booking):
        return f"/api/bookings/{booking.pk}/cancel/"

    def test_anonymous_cannot_cancel(self):
        booking = self._create()
        response = self.client.post(self._url(booking))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_consumer_cancels_own_pending_booking(self):
        booking = self._create()
        self.client.force_authenticate(self.consumer)
        response = self.client.post(self._url(booking))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response)["status"], Booking.Status.CANCELLED)
        self.assertEqual(page_rows(response)["refund_due_amount"], "0.00")
        self.assertIsNotNone(page_rows(response)["cancelled_at"])

    def test_cancel_confirmed_returns_the_refund_due(self):
        booking = self._create()
        confirm_booking(booking_id=booking.pk)
        self.client.force_authenticate(self.consumer)
        response = self.client.post(self._url(booking))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response)["status"], Booking.Status.CANCELLED)
        self.assertEqual(page_rows(response)["refund_due_amount"], "40.00")

    def test_another_consumers_booking_is_a_404(self):
        booking = self._create(owner=self.other, vehicle=self.other_vehicle)
        self.client.force_authenticate(self.consumer)
        response = self.client.post(self._url(booking))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(page_rows(response)["error"], "BOOKING_NOT_FOUND")

    def test_non_cancellable_state_is_a_409(self):
        booking = self._create()
        Booking.objects.filter(pk=booking.pk).update(
            status=Booking.Status.IN_PROGRESS
        )
        self.client.force_authenticate(self.consumer)
        response = self.client.post(self._url(booking))
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(page_rows(response)["error"], "BOOKING_NOT_CANCELLABLE")

    def test_repeat_cancel_is_idempotent(self):
        booking = self._create()
        self.client.force_authenticate(self.consumer)
        first = self.client.post(self._url(booking))
        second = self.client.post(self._url(booking))
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["status"], Booking.Status.CANCELLED)

    def test_manager_cannot_cancel(self):
        booking = self._create()
        manager = User.objects.create_user(
            email="manager@example.com",
            password="Tr0ub4dor&3",
            full_name="Manager",
            role=User.Role.MANAGER,
        )
        self.client.force_authenticate(manager)
        response = self.client.post(self._url(booking))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unknown_booking_is_a_404(self):
        self.client.force_authenticate(self.consumer)
        response = self.client.post("/api/bookings/999999/cancel/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(page_rows(response)["error"], "BOOKING_NOT_FOUND")

class ExtensionQuoteTests(TestCase):
    """``quote_extension``: the §19 whole-window recompute (increment 4.8, D54)."""

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
        BusinessRule.load()

    def _confirmed(self, *, start_hours=2, end_hours=4):
        now = timezone.now()
        booking = create_booking(
            slot_id=self.slot.id,
            start_time=now + timedelta(hours=start_hours),
            end_time=now + timedelta(hours=end_hours),
            user=self.consumer,
            vehicle=self.vehicle,
        )
        confirm_booking(booking_id=booking.pk)
        booking.refresh_from_db()
        return booking

    def test_recomputes_the_whole_window(self):
        # 2h booked; extend to 3.5h total -> the whole-window ceil is 4h, so the
        # charge is 2 extra hours, not the 1.5h slice rounded up.
        booking = self._confirmed()  # now+2h .. now+4h, 2h @ 20 = 40
        quote = quote_extension(
            booking=booking,
            new_end_time=booking.end_time + timedelta(hours=1, minutes=30),
        )
        self.assertEqual(quote.new_billed_hours, 4)
        self.assertEqual(quote.added_hours, 2)
        self.assertEqual(quote.extension_amount, Decimal("40.00"))
        self.assertEqual(quote.new_base_amount, Decimal("80.00"))

    def test_an_exact_hour_extension_adds_one_hour(self):
        booking = self._confirmed()
        quote = quote_extension(
            booking=booking, new_end_time=booking.end_time + timedelta(hours=1)
        )
        self.assertEqual(quote.added_hours, 1)
        self.assertEqual(quote.extension_amount, Decimal("20.00"))
        self.assertEqual(quote.new_base_amount, Decimal("60.00"))

    def test_refuses_a_time_that_does_not_lengthen(self):
        booking = self._confirmed()
        with self.assertRaises(InvalidExtensionError):
            quote_extension(booking=booking, new_end_time=booking.end_time)

    def test_refuses_an_end_time_that_is_still_in_the_past(self):
        now = timezone.now()
        booking = Booking(
            status=Booking.Status.CONFIRMED,
            slot=self.slot,
            start_time=now - timedelta(hours=5),
            end_time=now - timedelta(hours=3),
            billed_hours=2,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
        )
        with self.assertRaises(InvalidExtensionError):
            quote_extension(booking=booking, new_end_time=now - timedelta(hours=1))

    def test_refuses_beyond_the_slot_maximum(self):
        booking = self._confirmed()
        with self.assertRaises(MaxDurationExceededError):
            quote_extension(
                booking=booking,
                new_end_time=booking.start_time + timedelta(hours=30),
            )

    def test_enforces_the_slot_minimum(self):
        # A booking below the bay's minimum cannot be produced by creation, but
        # the shared rule still rejects it -- proving both ends are enforced.
        self.slot.min_booking_hours = 3
        self.slot.save(update_fields=["min_booking_hours"])
        now = timezone.now()
        booking = Booking(
            status=Booking.Status.CONFIRMED,
            slot=self.slot,
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=3),
            billed_hours=1,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("20.00"),
        )
        with self.assertRaises(MinDurationNotMetError):
            quote_extension(
                booking=booking,
                new_end_time=now + timedelta(hours=3, minutes=30),
            )

class ExtendBookingServiceTests(TestCase):
    """``extend_booking``: the paid-extension seam (increment 4.8, D54)."""

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

    def _create(self, *, owner=None, vehicle=None, start_hours=2, end_hours=4):
        owner = owner or self.consumer
        vehicle = vehicle or self.vehicle
        now = timezone.now()
        return create_booking(
            slot_id=self.slot.id,
            start_time=now + timedelta(hours=start_hours),
            end_time=now + timedelta(hours=end_hours),
            user=owner,
            vehicle=vehicle,
        )

    def _confirmed(self, **kwargs):
        booking = self._create(**kwargs)
        confirm_booking(booking_id=booking.pk)
        booking.refresh_from_db()
        return booking

    def test_extends_a_confirmed_booking(self):
        booking = self._confirmed()
        new_end = booking.end_time + timedelta(hours=1)
        extended = extend_booking(
            booking_id=booking.pk, user=self.consumer, new_end_time=new_end
        )
        self.assertEqual(extended.end_time, new_end)
        self.assertEqual(extended.billed_hours, 3)
        self.assertEqual(extended.base_amount, Decimal("60.00"))
        self.assertEqual(extended.status, Booking.Status.CONFIRMED)

    def test_extends_an_in_progress_booking(self):
        booking = self._confirmed()
        Booking.objects.filter(pk=booking.pk).update(
            status=Booking.Status.IN_PROGRESS
        )
        new_end = booking.end_time + timedelta(hours=1)
        extended = extend_booking(
            booking_id=booking.pk, user=self.consumer, new_end_time=new_end
        )
        self.assertEqual(extended.billed_hours, 3)
        self.assertEqual(extended.base_amount, Decimal("60.00"))

    def test_refuses_a_pending_booking(self):
        booking = self._create()  # PENDING_PAYMENT
        with self.assertRaises(BookingNotExtendableError) as caught:
            extend_booking(
                booking_id=booking.pk,
                user=self.consumer,
                new_end_time=booking.end_time + timedelta(hours=1),
            )
        self.assertEqual(caught.exception.code, "BOOKING_NOT_EXTENDABLE")

    def test_refuses_every_other_state(self):
        for state in (
            Booking.Status.COMPLETED,
            Booking.Status.CANCELLED,
            Booking.Status.EXPIRED,
            Booking.Status.TERMINATED,
        ):
            with self.subTest(state=state):
                booking = self._confirmed()
                Booking.objects.filter(pk=booking.pk).update(status=state)
                with self.assertRaises(BookingNotExtendableError):
                    extend_booking(
                        booking_id=booking.pk,
                        user=self.consumer,
                        new_end_time=booking.end_time + timedelta(hours=1),
                    )

    def test_extension_conflicts_with_the_next_booking(self):
        booking = self._confirmed()
        # Adjacent booking: starts exactly when the first ends, so creation is
        # allowed (half-open windows, D41) -- but it blocks the extension.
        self._create(start_hours=4, end_hours=6)
        with self.assertRaises(BookingConflictError):
            extend_booking(
                booking_id=booking.pk,
                user=self.consumer,
                new_end_time=booking.end_time + timedelta(hours=1),
            )

    def test_retrying_the_same_extension_is_a_no_op(self):
        booking = self._confirmed()
        new_end = booking.end_time + timedelta(hours=1)
        first = extend_booking(
            booking_id=booking.pk, user=self.consumer, new_end_time=new_end
        )
        second = extend_booking(
            booking_id=booking.pk, user=self.consumer, new_end_time=new_end
        )
        self.assertEqual(second.billed_hours, first.billed_hours)
        self.assertEqual(second.base_amount, first.base_amount)

    def test_shrinking_is_refused(self):
        booking = self._confirmed()
        with self.assertRaises(InvalidExtensionError):
            extend_booking(
                booking_id=booking.pk,
                user=self.consumer,
                new_end_time=booking.end_time - timedelta(hours=1),
            )

    def test_refuses_beyond_the_slot_maximum(self):
        booking = self._confirmed()
        with self.assertRaises(MaxDurationExceededError):
            extend_booking(
                booking_id=booking.pk,
                user=self.consumer,
                new_end_time=booking.start_time + timedelta(hours=30),
            )

    def test_another_consumers_booking_is_not_found(self):
        booking = self._create(owner=self.other, vehicle=self.other_vehicle)
        with self.assertRaises(BookingNotFoundError):
            extend_booking(
                booking_id=booking.pk,
                user=self.consumer,
                new_end_time=booking.end_time + timedelta(hours=1),
            )

    def test_unknown_booking_is_not_found(self):
        with self.assertRaises(BookingNotFoundError):
            extend_booking(
                booking_id=999999,
                user=self.consumer,
                new_end_time=timezone.now() + timedelta(hours=5),
            )

    def test_a_full_refund_after_extension_uses_the_new_total(self):
        # The seam only bumps base_amount once the extension is paid, so a later
        # cancellation refunds what was actually paid (D54/D53).
        booking = self._confirmed()
        extend_booking(
            booking_id=booking.pk,
            user=self.consumer,
            new_end_time=booking.end_time + timedelta(hours=1),
        )
        cancelled = cancel_booking(booking_id=booking.pk, user=self.consumer)
        self.assertEqual(cancelled.base_amount, Decimal("60.00"))
        self.assertEqual(cancelled.refund_due_amount, Decimal("60.00"))

class ExtensionQuoteApiTests(TestCase):
    """``GET /api/bookings/{id}/extension-quote/`` (increment 4.8, D54)."""

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
        BusinessRule.load()

    def setUp(self):
        self.client = APIClient()

    def _confirmed(self, *, owner=None, vehicle=None):
        owner = owner or self.consumer
        vehicle = vehicle or self.vehicle
        now = timezone.now()
        booking = create_booking(
            slot_id=self.slot.id,
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=4),
            user=owner,
            vehicle=vehicle,
        )
        confirm_booking(booking_id=booking.pk)
        booking.refresh_from_db()
        return booking

    def _get(self, booking, new_end):
        return self.client.get(
            f"/api/bookings/{booking.pk}/extension-quote/",
            {"end_time": new_end.isoformat()},
        )

    def test_anonymous_cannot_quote(self):
        booking = self._confirmed()
        response = self._get(booking, booking.end_time + timedelta(hours=1))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_gets_the_quote(self):
        booking = self._confirmed()
        self.client.force_authenticate(self.consumer)
        response = self._get(booking, booking.end_time + timedelta(hours=1))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response)["added_hours"], 1)
        self.assertEqual(page_rows(response)["extension_amount"], "20.00")
        self.assertEqual(page_rows(response)["new_base_amount"], "60.00")

    def test_another_consumers_booking_is_a_404(self):
        booking = self._confirmed()
        self.client.force_authenticate(self.other)
        response = self._get(booking, booking.end_time + timedelta(hours=1))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(page_rows(response)["error"], "BOOKING_NOT_FOUND")

    def test_non_lengthening_end_time_is_a_400(self):
        booking = self._confirmed()
        self.client.force_authenticate(self.consumer)
        response = self._get(booking, booking.end_time)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(page_rows(response)["error"], "INVALID_EXTENSION")

    def test_manager_cannot_quote(self):
        booking = self._confirmed()
        manager = User.objects.create_user(
            email="manager@example.com",
            password="Tr0ub4dor&3",
            full_name="Manager",
            role=User.Role.MANAGER,
        )
        self.client.force_authenticate(manager)
        response = self._get(booking, booking.end_time + timedelta(hours=1))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class BookingHistoryQueryTests(TestCase):
    """``services.filter_bookings`` -- history queryset refinement (4.9)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        cls.lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
        )
        cls.other_lot = ParkingLot.objects.create(
            city=city, number=2, name="Church Street", address_line="2 Church St",
        )
        cls.slot = ParkingSlot.objects.create(
            lot=cls.lot, number="A-01", slot_type=ParkingSlot.SlotType.REGULAR,
        )
        cls.other_slot = ParkingSlot.objects.create(
            lot=cls.other_lot, number="B-01", slot_type=ParkingSlot.SlotType.REGULAR,
        )
        cls.consumer = User.objects.create_user(
            email="consumer@example.com",
            password="Tr0ub4dor&3",
            full_name="Consumer",
        )
        cls.vehicle = Vehicle.objects.create(
            owner=cls.consumer, registration_number="KA01AB1234",
        )

    def _booking(
        self, *, booking_status=Booking.Status.PENDING_PAYMENT,
        start_hours=2, end_hours=3, slot=None,
    ):
        now = timezone.now()
        hours = end_hours - start_hours
        return Booking.objects.create(
            user=self.consumer,
            created_by=self.consumer,
            vehicle=self.vehicle,
            vehicle_plate="",
            slot=slot or self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=start_hours),
            end_time=now + timedelta(hours=end_hours),
            billed_hours=hours,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("20.00") * hours,
            status=booking_status,
        )

    def test_status_filter_matches_stored_status(self):
        self._booking(booking_status=Booking.Status.PENDING_PAYMENT)
        confirmed = self._booking(
            booking_status=Booking.Status.CONFIRMED, start_hours=4, end_hours=5,
        )
        ids = set(
            filter_bookings(
                Booking.objects.all(), statuses=[Booking.Status.CONFIRMED]
            ).values_list("id", flat=True)
        )
        self.assertEqual(ids, {confirmed.id})

    def test_status_filter_accepts_several(self):
        confirmed = self._booking(booking_status=Booking.Status.CONFIRMED)
        in_progress = self._booking(
            booking_status=Booking.Status.IN_PROGRESS, start_hours=4, end_hours=5,
        )
        self._booking(
            booking_status=Booking.Status.CANCELLED, start_hours=6, end_hours=7,
        )
        ids = set(
            filter_bookings(
                Booking.objects.all(),
                statuses=[Booking.Status.CONFIRMED, Booking.Status.IN_PROGRESS],
            ).values_list("id", flat=True)
        )
        self.assertEqual(ids, {confirmed.id, in_progress.id})

    def test_scope_windows(self):
        past = self._booking(
            booking_status=Booking.Status.COMPLETED, start_hours=-4, end_hours=-2,
        )
        ongoing = self._booking(
            booking_status=Booking.Status.IN_PROGRESS, start_hours=-1, end_hours=1,
        )
        upcoming = self._booking(
            booking_status=Booking.Status.CONFIRMED, start_hours=2, end_hours=3,
        )

        def ids(scope):
            return set(
                filter_bookings(Booking.objects.all(), scope=scope).values_list(
                    "id", flat=True
                )
            )

        self.assertEqual(ids("past"), {past.id})
        self.assertEqual(ids("ongoing"), {ongoing.id})
        self.assertEqual(ids("upcoming"), {upcoming.id})

    def test_scope_combines_with_status(self):
        upcoming_confirmed = self._booking(
            booking_status=Booking.Status.CONFIRMED, start_hours=3, end_hours=4,
        )
        self._booking(
            booking_status=Booking.Status.CANCELLED, start_hours=5, end_hours=6,
        )
        ids = set(
            filter_bookings(
                Booking.objects.all(),
                statuses=[Booking.Status.CONFIRMED],
                scope="upcoming",
            ).values_list("id", flat=True)
        )
        self.assertEqual(ids, {upcoming_confirmed.id})

    def test_lot_filter(self):
        in_lot = self._booking(booking_status=Booking.Status.CONFIRMED)
        self._booking(
            booking_status=Booking.Status.CONFIRMED, start_hours=4, end_hours=5,
            slot=self.other_slot,
        )
        ids = set(
            filter_bookings(
                Booking.objects.all(), lot_id=self.lot.id
            ).values_list("id", flat=True)
        )
        self.assertEqual(ids, {in_lot.id})

    def test_ordering_is_applied_with_stable_tiebreak(self):
        first = self._booking(booking_status=Booking.Status.CONFIRMED)
        second = self._booking(
            booking_status=Booking.Status.CONFIRMED, start_hours=4, end_hours=5,
        )
        ordered = list(
            filter_bookings(
                Booking.objects.all(), ordering="-start_time"
            ).values_list("id", flat=True)
        )
        self.assertEqual(ordered, [second.id, first.id])

    def test_lapsed_hold_keeps_its_stored_status_for_filtering(self):
        # 4.9/Q5: the filter is on the stored status; a lapsed hold still matches
        # PENDING_PAYMENT even though effective_status reads EXPIRED.
        now = timezone.now()
        booking = Booking.objects.create(
            user=self.consumer,
            created_by=self.consumer,
            vehicle=self.vehicle,
            vehicle_plate="",
            slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=3),
            billed_hours=1,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("20.00"),
            status=Booking.Status.PENDING_PAYMENT,
            hold_expires_at=now - timedelta(minutes=1),
        )
        ids = set(
            filter_bookings(
                Booking.objects.all(), statuses=[Booking.Status.PENDING_PAYMENT]
            ).values_list("id", flat=True)
        )
        self.assertIn(booking.id, ids)
        self.assertEqual(effective_status(booking), Booking.Status.EXPIRED)


class BookingHistoryApiTests(TestCase):
    """``GET /api/bookings/`` history filters (increment 4.9)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
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
            city=city, number=1, name="MG Road", address_line="1 MG Road",
            manager=cls.manager,
        )
        cls.other_lot = ParkingLot.objects.create(
            city=city, number=2, name="Indiranagar",
            address_line="2 100ft Road",
        )
        cls.slot = ParkingSlot.objects.create(
            lot=cls.lot, number="A-01", slot_type=ParkingSlot.SlotType.REGULAR,
        )
        cls.other_slot = ParkingSlot.objects.create(
            lot=cls.other_lot, number="B-01",
            slot_type=ParkingSlot.SlotType.REGULAR,
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

    def _booking(
        self, *, owner=None, booking_status=Booking.Status.PENDING_PAYMENT,
        slot=None, start_hours=2, end_hours=3,
    ):
        owner = owner or self.consumer
        slot = slot or self.slot
        now = timezone.now()
        hours = end_hours - start_hours
        return Booking.objects.create(
            user=owner,
            created_by=owner,
            vehicle=self.vehicle if owner == self.consumer else self.other_vehicle,
            vehicle_plate="",
            slot=slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=start_hours),
            end_time=now + timedelta(hours=end_hours),
            billed_hours=hours,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("20.00") * hours,
            status=booking_status,
        )

    def test_anonymous_cannot_list(self):
        response = self.client.get("/api/bookings/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_returns_only_own_bookings_with_lot_name(self):
        mine = self._booking()
        self._booking(owner=self.other, start_hours=4, end_hours=5)
        self.client.force_authenticate(self.consumer)
        response = self.client.get("/api/bookings/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in page_rows(response)], [mine.id])
        self.assertEqual(page_rows(response)[0]["lot_name"], "MG Road")

    def test_status_filter(self):
        confirmed = self._booking(booking_status=Booking.Status.CONFIRMED)
        self._booking(
            booking_status=Booking.Status.CANCELLED, start_hours=4, end_hours=5,
        )
        self.client.force_authenticate(self.consumer)
        response = self.client.get("/api/bookings/", {"status": "CONFIRMED"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in page_rows(response)], [confirmed.id])

    def test_status_filter_accepts_multiple_values(self):
        confirmed = self._booking(booking_status=Booking.Status.CONFIRMED)
        in_progress = self._booking(
            booking_status=Booking.Status.IN_PROGRESS, start_hours=4, end_hours=5,
        )
        self._booking(
            booking_status=Booking.Status.CANCELLED, start_hours=6, end_hours=7,
        )
        self.client.force_authenticate(self.consumer)
        response = self.client.get(
            "/api/bookings/", {"status": "CONFIRMED,IN_PROGRESS"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {row["id"] for row in page_rows(response)}, {confirmed.id, in_progress.id}
        )

    def test_unknown_status_is_a_400(self):
        self.client.force_authenticate(self.consumer)
        response = self.client.get("/api/bookings/", {"status": "NOPE"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_scope_filter(self):
        past = self._booking(
            booking_status=Booking.Status.COMPLETED, start_hours=-4, end_hours=-2,
        )
        self._booking(
            booking_status=Booking.Status.CONFIRMED, start_hours=2, end_hours=3,
        )
        self.client.force_authenticate(self.consumer)
        response = self.client.get("/api/bookings/", {"scope": "past"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in page_rows(response)], [past.id])

    def test_invalid_scope_is_a_400(self):
        self.client.force_authenticate(self.consumer)
        response = self.client.get("/api/bookings/", {"scope": "someday"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_ordering_is_a_400(self):
        self.client.force_authenticate(self.consumer)
        response = self.client.get("/api/bookings/", {"ordering": "plate"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_manager_may_list(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/bookings/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_manager_sees_only_assigned_lots(self):
        mine = self._booking()
        self._booking(
            owner=self.other, slot=self.other_slot, start_hours=4, end_hours=5,
        )
        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/bookings/")
        self.assertEqual([row["id"] for row in page_rows(response)], [mine.id])

    def test_manager_shape_names_the_payer(self):
        self._booking()
        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/bookings/")
        row = page_rows(response)[0]
        self.assertEqual(row["consumer_email"], self.consumer.email)
        self.assertEqual(row["consumer_name"], "Consumer")
        self.assertEqual(row["lot"], self.lot.id)
        self.assertEqual(row["vehicle_plate"], "KA01AB1234")

    def test_manager_lot_filter_cannot_reach_an_unassigned_lot(self):
        self._booking(owner=self.other, slot=self.other_slot)
        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/bookings/", {"lot": self.other_lot.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response), [])

    def test_admin_sees_all(self):
        self._booking()
        self._booking(
            owner=self.other, slot=self.other_slot, start_hours=4, end_hours=5,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/bookings/")
        self.assertEqual(len(page_rows(response)), 2)

    def test_consumer_row_names_no_payer(self):
        self._booking()
        self.client.force_authenticate(self.consumer)
        response = self.client.get("/api/bookings/")
        self.assertNotIn("consumer_email", page_rows(response)[0])


class BookingDetailApiTests(TestCase):
    """``GET /api/bookings/{id}/`` (increment 4.9)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        cls.lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
            state="Karnataka", postal_code="560001",
        )
        cls.slot = ParkingSlot.objects.create(
            lot=cls.lot, number="A-01", slot_type=ParkingSlot.SlotType.REGULAR,
            floor="G",
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
        BusinessRule.load()

    def setUp(self):
        self.client = APIClient()

    def _pending(self):
        now = timezone.now()
        return create_booking(
            slot_id=self.slot.id,
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=4),
            user=self.consumer,
            vehicle=self.vehicle,
        )

    def _confirmed(self):
        booking = self._pending()
        confirm_booking(booking_id=booking.pk)
        booking.refresh_from_db()
        return booking

    def test_anonymous_cannot_read(self):
        booking = self._confirmed()
        response = self.client.get(f"/api/bookings/{booking.pk}/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_reads_rich_detail(self):
        booking = self._confirmed()
        self.client.force_authenticate(self.consumer)
        response = self.client.get(f"/api/bookings/{booking.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response)["reference"], booking.reference)
        self.assertEqual(page_rows(response)["effective_status"], Booking.Status.CONFIRMED)
        # Rich detail fields (4.9/Q3).
        self.assertEqual(page_rows(response)["lot"], self.lot.id)
        self.assertEqual(page_rows(response)["lot_name"], "MG Road")
        self.assertEqual(page_rows(response)["lot_address_line"], "1 MG Road")
        self.assertEqual(page_rows(response)["lot_city"], "Bengaluru")
        self.assertEqual(page_rows(response)["lot_state"], "Karnataka")
        self.assertEqual(page_rows(response)["lot_postal_code"], "560001")
        self.assertEqual(page_rows(response)["slot_floor"], "G")
        self.assertTrue(page_rows(response)["can_cancel"])
        self.assertTrue(page_rows(response)["can_extend"])

    def test_pending_action_flags(self):
        booking = self._pending()
        self.client.force_authenticate(self.consumer)
        response = self.client.get(f"/api/bookings/{booking.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(page_rows(response)["can_cancel"])
        self.assertFalse(page_rows(response)["can_extend"])

    def test_cancelled_booking_has_no_actions(self):
        booking = self._confirmed()
        cancel_booking(booking_id=booking.pk, user=self.consumer)
        self.client.force_authenticate(self.consumer)
        response = self.client.get(f"/api/bookings/{booking.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(page_rows(response)["can_cancel"])
        self.assertFalse(page_rows(response)["can_extend"])

    def test_another_consumers_booking_is_a_404_with_the_booking_code(self):
        booking = self._confirmed()
        self.client.force_authenticate(self.other)
        response = self.client.get(f"/api/bookings/{booking.pk}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(page_rows(response)["error"], "BOOKING_NOT_FOUND")

    def test_unknown_booking_is_a_404(self):
        self.client.force_authenticate(self.consumer)
        response = self.client.get("/api/bookings/999999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(page_rows(response)["error"], "BOOKING_NOT_FOUND")

    def test_manager_cannot_read(self):
        booking = self._confirmed()
        manager = User.objects.create_user(
            email="manager@example.com",
            password="Tr0ub4dor&3",
            full_name="Manager",
            role=User.Role.MANAGER,
        )
        self.client.force_authenticate(manager)
        response = self.client.get(f"/api/bookings/{booking.pk}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class BookingEntryExitApiTests(TestCase):
    """Check-in / check-out of the simulated gate (6.3, D69)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        cls.manager = User.objects.create_user(
            email="manager@example.com", password="Tr0ub4dor&3",
            full_name="Manager", role=User.Role.MANAGER,
        )
        cls.other_manager = User.objects.create_user(
            email="othermanager@example.com", password="Tr0ub4dor&3",
            full_name="Other Manager", role=User.Role.MANAGER,
        )
        cls.consumer = User.objects.create_user(
            email="consumer@example.com", password="Tr0ub4dor&3",
            full_name="Consumer",
        )
        cls.admin = User.objects.create_user(
            email="admin@example.com", password="Tr0ub4dor&3",
            full_name="Admin", role=User.Role.ADMIN,
        )
        cls.lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
            manager=cls.manager,
        )
        cls.slot = ParkingSlot.objects.create(
            lot=cls.lot, number="A-01", slot_type=ParkingSlot.SlotType.REGULAR,
        )
        Tariff.objects.create(
            lot=cls.lot, slot_type=ParkingSlot.SlotType.REGULAR,
            hourly_rate=Decimal("20.00"),
        )
        cls.vehicle = Vehicle.objects.create(
            owner=cls.consumer, registration_number="KA01AB1234",
        )
        BusinessRule.load()

    def setUp(self):
        self.client = APIClient()

    def _confirmed(self):
        now = timezone.now()
        booking = create_booking(
            slot_id=self.slot.id,
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=4),
            user=self.consumer,
            vehicle=self.vehicle,
        )
        confirm_booking(booking_id=booking.pk)
        booking.refresh_from_db()
        return booking

    def _post(self, action, booking, as_user):
        self.client.force_authenticate(as_user)
        return self.client.post(f"/api/bookings/{booking.pk}/{action}/")

    # --- authorisation / scope ------------------------------------------

    def test_anonymous_cannot_check_in(self):
        booking = self._confirmed()
        response = self.client.post(f"/api/bookings/{booking.pk}/check-in/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_consumer_cannot_check_in(self):
        booking = self._confirmed()
        response = self._post("check-in", booking, self.consumer)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_check_in(self):
        booking = self._confirmed()
        response = self._post("check-in", booking, self.admin)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassigned_manager_gets_404(self):
        booking = self._confirmed()
        response = self._post("check-in", booking, self.other_manager)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(page_rows(response)["error"], "BOOKING_NOT_FOUND")

    def test_unknown_booking_is_404(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self.client.post("/api/bookings/999999/check-in/").status_code,
            status.HTTP_404_NOT_FOUND,
        )

    # --- check-in -------------------------------------------------------

    def test_manager_checks_in_a_confirmed_booking(self):
        booking = self._confirmed()
        response = self._post("check-in", booking, self.manager)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response)["status"], Booking.Status.IN_PROGRESS)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.IN_PROGRESS)
        self.assertIsNotNone(booking.actual_entry_at)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, ParkingSlot.Status.OCCUPIED)

    def test_check_in_is_idempotent(self):
        booking = self._confirmed()
        first = self._post("check-in", booking, self.manager)
        entry = page_rows(first)["actual_entry_at"]
        second = self._post("check-in", booking, self.manager)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(second)["actual_entry_at"], entry)

    def test_pending_booking_cannot_check_in(self):
        now = timezone.now()
        booking = create_booking(
            slot_id=self.slot.id,
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=4),
            user=self.consumer, vehicle=self.vehicle,
        )
        response = self._post("check-in", booking, self.manager)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(page_rows(response)["error"], "BOOKING_NOT_CHECKINABLE")

    # --- check-out ------------------------------------------------------

    def test_manager_checks_out_an_in_progress_booking(self):
        booking = self._confirmed()
        self._post("check-in", booking, self.manager)
        response = self._post("check-out", booking, self.manager)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_rows(response)["status"], Booking.Status.COMPLETED)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.COMPLETED)
        self.assertIsNotNone(booking.actual_exit_at)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, ParkingSlot.Status.AVAILABLE)

    def test_check_out_is_idempotent(self):
        booking = self._confirmed()
        self._post("check-in", booking, self.manager)
        first = self._post("check-out", booking, self.manager)
        second = self._post("check-out", booking, self.manager)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)

    def test_confirmed_booking_cannot_check_out(self):
        booking = self._confirmed()
        response = self._post("check-out", booking, self.manager)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(page_rows(response)["error"], "BOOKING_NOT_CHECKOUTABLE")

    # --- occupancy composition (D68) ------------------------------------

    def test_entry_does_not_override_out_of_service(self):
        booking = self._confirmed()
        self.slot.status = ParkingSlot.Status.OUT_OF_SERVICE
        self.slot.save(update_fields=["status"])
        self._post("check-in", booking, self.manager)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, ParkingSlot.Status.OUT_OF_SERVICE)

    # --- operator hints -------------------------------------------------

    def test_operator_row_has_entry_exit_hints(self):
        booking = self._confirmed()
        self.client.force_authenticate(self.manager)
        row = page_rows(self.client.get("/api/bookings/"))[0]
        self.assertTrue(row["can_check_in"])
        self.assertFalse(row["can_check_out"])

        self._post("check-in", booking, self.manager)
        row = page_rows(self.client.get("/api/bookings/"))[0]
        self.assertFalse(row["can_check_in"])
        self.assertTrue(row["can_check_out"])