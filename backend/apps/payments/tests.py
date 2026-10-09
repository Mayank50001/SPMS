"""Payments tests.

5.1 model tests (persistence, snapshot constraints, the ""->NULL rule) and 5.2
gateway tests (the offline MockGateway and the stdlib Razorpay signature check).
The real Razorpay adapter's network calls are exercised by opt-in sandbox
integration tests, not here (D58).
"""

import hashlib
import hmac
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.parking.models import City, ParkingLot, ParkingSlot

from apps.payments.gateway import (
    MockGateway,
    PaymentGatewayError,
    get_payment_gateway,
    verify_razorpay_signature,
)
from apps.payments.models import Payment

class PaymentModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Phase 3 gotcha: a data migration seeds City rows when the test DB is
        # built, so clear them before creating our own.
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
        )
        slot = ParkingSlot.objects.create(
            lot=lot, number="A-01", slot_type=ParkingSlot.SlotType.REGULAR,
        )
        user = User.objects.create_user(
            email="consumer@example.com",
            password="Tr0ub4dor&3",
            full_name="Consumer",
        )
        now = timezone.now()
        cls.booking = Booking.objects.create(
            user=user,
            created_by=user,
            vehicle=None,
            vehicle_plate="KA01AB1234",
            slot=slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            billed_hours=2,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
        )

    # ---- defaults ----------------------------------------------------------

    def test_defaults(self):
        payment = Payment.objects.create(
            booking=self.booking, amount=Decimal("40.00"),
        )
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.purpose, Payment.Purpose.BOOKING)
        self.assertEqual(payment.method, Payment.Method.ONLINE)
        self.assertEqual(payment.currency, "INR")

    # ---- constraints -------------------------------------------------------

    def test_amount_must_be_positive(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.create(
                    booking=self.booking, amount=Decimal("0.00"),
                )

    def test_cash_payment_cannot_carry_provider_ids(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.create(
                    booking=self.booking,
                    amount=Decimal("10.00"),
                    method=Payment.Method.CASH,
                    provider_order_id="order_x",
                )

    def test_blank_provider_ids_become_null(self):
        payment = Payment.objects.create(
            booking=self.booking,
            amount=Decimal("10.00"),
            method=Payment.Method.CASH,
            provider_order_id="",
            provider_payment_id="",
        )
        payment.refresh_from_db()
        self.assertIsNone(payment.provider_order_id)
        self.assertIsNone(payment.provider_payment_id)

    def test_two_cash_payments_do_not_collide(self):
        Payment.objects.create(
            booking=self.booking, amount=Decimal("10.00"),
            method=Payment.Method.CASH,
        )
        Payment.objects.create(
            booking=self.booking, amount=Decimal("20.00"),
            method=Payment.Method.CASH,
        )
        self.assertEqual(self.booking.payments.count(), 2)

    def test_provider_order_id_is_unique(self):
        Payment.objects.create(
            booking=self.booking, amount=Decimal("10.00"),
            provider_order_id="order_1",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.create(
                    booking=self.booking, amount=Decimal("10.00"),
                    provider_order_id="order_1",
                )

    def test_booking_with_payment_cannot_be_deleted(self):
        Payment.objects.create(
            booking=self.booking, amount=Decimal("10.00"),
        )
        with self.assertRaises(ProtectedError):
            self.booking.delete()

class MockGatewayTests(SimpleTestCase):
    def setUp(self):
        self.gateway = MockGateway()

    def test_create_returns_order_and_echoes_amount(self):
        result = self.gateway.create_payment(
            amount=Decimal("40.00"), currency="INR", receipt="BK-1",
        )
        self.assertTrue(result.gateway_order_id.startswith("order_mock_"))
        self.assertEqual(result.client_payload["amount"], "40.00")
        self.assertEqual(result.client_payload["currency"], "INR")

    def test_verify_succeeds_by_default(self):
        result = self.gateway.verify_payment(
            gateway_order_id="order_mock_1", payload={},
        )
        self.assertTrue(result.success)
        self.assertTrue(result.gateway_payment_id.startswith("pay_mock_"))

    def test_verify_can_be_forced_to_fail(self):
        result = self.gateway.verify_payment(
            gateway_order_id="order_mock_1", payload={"outcome": "failure"},
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_reason, "mock_declined")

    def test_refund_echoes_amount(self):
        result = self.gateway.refund_payment(
            gateway_payment_id="pay_mock_1", amount=Decimal("40.00"),
        )
        self.assertTrue(result.refund_id.startswith("rfnd_mock_"))
        self.assertEqual(result.amount, Decimal("40.00"))

class RazorpaySignatureTests(SimpleTestCase):
    def test_valid_signature_is_accepted(self):
        secret, order_id, payment_id = "test_secret", "order_123", "pay_456"
        signature = hmac.new(
            secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        self.assertTrue(
            verify_razorpay_signature(
                order_id=order_id, payment_id=payment_id,
                signature=signature, secret=secret,
            )
        )

    def test_bad_signature_is_rejected(self):
        self.assertFalse(
            verify_razorpay_signature(
                order_id="order_123", payment_id="pay_456",
                signature="deadbeef", secret="test_secret",
            )
        )

    def test_missing_values_are_rejected(self):
        self.assertFalse(
            verify_razorpay_signature(
                order_id="", payment_id="", signature="", secret="",
            )
        )


class GatewaySelectionTests(SimpleTestCase):
    @override_settings(PAYMENT_GATEWAY="mock")
    def test_mock_is_selected_by_name(self):
        self.assertIsInstance(get_payment_gateway(), MockGateway)

    @override_settings(PAYMENT_GATEWAY="nonsense")
    def test_unknown_name_raises(self):
        with self.assertRaises(PaymentGatewayError):
            get_payment_gateway()


class RazorpayGatewayConfigTests(SimpleTestCase):
    @override_settings(PAYMENT_GATEWAY="razorpay")
    def test_selecting_razorpay_without_sdk_or_keys_raises_cleanly(self):
        # Environment-independent: either the SDK is missing or the keys are;
        # both must surface as PaymentGatewayError, never an unhandled error.
        with self.assertRaises(PaymentGatewayError):
            get_payment_gateway()

class PaymentCreationApiTests(TestCase):
    """``POST /api/payments/`` (increment 5.3, D59)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
        )
        cls.slot = ParkingSlot.objects.create(
            lot=lot, number="A-01", slot_type=ParkingSlot.SlotType.REGULAR,
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
        cls.manager = User.objects.create_user(
            email="manager@example.com",
            password="Tr0ub4dor&3",
            full_name="Manager",
            role=User.Role.MANAGER,
        )

    def setUp(self):
        self.client = APIClient()
        now = timezone.now()
        self.booking = Booking.objects.create(
            user=self.consumer,
            created_by=self.consumer,
            vehicle=None,
            vehicle_plate="KA01AB1234",
            slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            billed_hours=2,
            hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
            status=Booking.Status.PENDING_PAYMENT,
            hold_expires_at=now + timedelta(minutes=5),
        )

    def _post(self, payload=None):
        return self.client.post(
            "/api/payments/",
            payload if payload is not None else {"booking": self.booking.id},
            format="json",
        )

    def test_anonymous_is_rejected(self):
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_manager_is_rejected(self):
        self.client.force_authenticate(self.manager)
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_consumer_starts_a_payment(self):
        self.client.force_authenticate(self.consumer)
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Payment.Status.PENDING)
        self.assertEqual(response.data["method"], Payment.Method.ONLINE)
        self.assertEqual(response.data["purpose"], Payment.Purpose.BOOKING)
        self.assertEqual(Decimal(response.data["amount"]), Decimal("40.00"))
        self.assertEqual(response.data["currency"], "INR")
        self.assertTrue(response.data["provider_order_id"].startswith("order_mock_"))
        self.assertEqual(response.data["client_payload"]["gateway"], "mock")

        payment = Payment.objects.get(pk=response.data["id"])
        self.assertEqual(payment.booking, self.booking)
        self.assertEqual(payment.amount, Decimal("40.00"))

    def test_amount_is_server_side(self):
        # A client-supplied amount/currency is ignored (D57/§46).
        self.client.force_authenticate(self.consumer)
        response = self._post(
            {"booking": self.booking.id, "amount": "0.01", "currency": "USD"}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(response.data["amount"]), Decimal("40.00"))
        self.assertEqual(response.data["currency"], "INR")

    def test_foreign_booking_is_a_404(self):
        self.client.force_authenticate(self.other)
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"], "BOOKING_NOT_FOUND")

    def test_unknown_booking_is_a_404(self):
        self.client.force_authenticate(self.consumer)
        response = self._post({"booking": 999999})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_confirmed_booking_is_not_payable(self):
        self.booking.status = Booking.Status.CONFIRMED
        self.booking.hold_expires_at = None
        self.booking.save(update_fields=["status", "hold_expires_at"])
        self.client.force_authenticate(self.consumer)
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"], "BOOKING_NOT_PAYABLE")

    def test_lapsed_hold_is_not_payable(self):
        self.booking.hold_expires_at = timezone.now() - timedelta(minutes=1)
        self.booking.save(update_fields=["hold_expires_at"])
        self.client.force_authenticate(self.consumer)
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"], "BOOKING_NOT_PAYABLE")

    def test_already_succeeded_is_refused(self):
        Payment.objects.create(
            booking=self.booking,
            amount=Decimal("40.00"),
            status=Payment.Status.SUCCEEDED,
            provider_order_id="order_paid_1",
            provider_payment_id="pay_paid_1",
        )
        self.client.force_authenticate(self.consumer)
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"], "BOOKING_ALREADY_PAID")

    @override_settings(PAYMENT_GATEWAY="razorpay")
    def test_gateway_unavailable_is_a_503_and_writes_no_row(self):
        # No SDK/keys in the test env, so resolving the adapter raises before
        # any Payment row is written.
        self.client.force_authenticate(self.consumer)
        before = Payment.objects.count()
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["error"], "PAYMENT_GATEWAY_UNAVAILABLE")
        self.assertEqual(Payment.objects.count(), before)

    def test_repeat_requests_get_distinct_order_ids(self):
        # Regression for the shared mock counter (D59): two attempts must not
        # collide on the unique provider_order_id.
        self.client.force_authenticate(self.consumer)
        first = self._post()
        second = self._post()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(
            first.data["provider_order_id"], second.data["provider_order_id"]
        )
        self.assertEqual(self.booking.payments.count(), 2)