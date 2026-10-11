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
import json
from unittest.mock import patch

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
    MOCK_WEBHOOK_HEADER,
    MOCK_WEBHOOK_SIGNATURE,
    WebhookEvent,
    verify_razorpay_webhook_signature,
)
from apps.payments.models import Payment, Refund

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

class WebhookSignatureTests(SimpleTestCase):
    """The stdlib raw-body check (D60)."""

    def test_valid_signature_is_accepted(self):
        secret, body = "whsec", b'{"event":"payment.captured"}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertTrue(
            verify_razorpay_webhook_signature(
                body=body, signature=signature, secret=secret
            )
        )

    def test_bad_signature_is_rejected(self):
        self.assertFalse(
            verify_razorpay_webhook_signature(
                body=b"{}", signature="deadbeef", secret="whsec"
            )
        )

    def test_missing_values_are_rejected(self):
        self.assertFalse(
            verify_razorpay_webhook_signature(body=b"", signature="", secret="")
        )


class MockWebhookParseTests(SimpleTestCase):
    def setUp(self):
        self.gateway = MockGateway()

    def _body(self, event, order_id, payment_id):
        return json.dumps(
            {
                "event": event,
                "payload": {
                    "payment": {
                        "entity": {"id": payment_id, "order_id": order_id}
                    }
                },
            }
        ).encode()

    def test_unsigned_webhook_is_refused(self):
        self.assertIsNone(
            self.gateway.parse_webhook(body=b"{}", headers={})
        )

    def test_captured_event_is_success(self):
        event = self.gateway.parse_webhook(
            body=self._body("payment.captured", "order_1", "pay_1"),
            headers={MOCK_WEBHOOK_HEADER: MOCK_WEBHOOK_SIGNATURE},
        )
        self.assertIsInstance(event, WebhookEvent)
        self.assertTrue(event.success)
        self.assertEqual(event.gateway_order_id, "order_1")
        self.assertEqual(event.gateway_payment_id, "pay_1")

    def test_failed_event_is_not_success(self):
        event = self.gateway.parse_webhook(
            body=self._body("payment.failed", "order_1", "pay_1"),
            headers={MOCK_WEBHOOK_HEADER: MOCK_WEBHOOK_SIGNATURE},
        )
        self.assertFalse(event.success)

class PaymentConfirmationApiTests(TestCase):
    """``POST /api/payments/{id}/confirm/`` (increment 5.4, D60)."""

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
            email="consumer@example.com", password="Tr0ub4dor&3",
            full_name="Consumer",
        )
        cls.other = User.objects.create_user(
            email="other@example.com", password="Tr0ub4dor&3",
            full_name="Other",
        )
        cls.manager = User.objects.create_user(
            email="manager@example.com", password="Tr0ub4dor&3",
            full_name="Manager", role=User.Role.MANAGER,
        )

    def setUp(self):
        self.client = APIClient()
        now = timezone.now()
        self.booking = Booking.objects.create(
            user=self.consumer, created_by=self.consumer, vehicle=None,
            vehicle_plate="KA01AB1234", slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            billed_hours=2, hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
            status=Booking.Status.PENDING_PAYMENT,
            hold_expires_at=now + timedelta(minutes=5),
        )
        self.payment = Payment.objects.create(
            booking=self.booking, amount=Decimal("40.00"),
            provider_order_id="order_mock_000001",
        )

    def _post(self, payload=None, payment_id=None):
        return self.client.post(
            f"/api/payments/{payment_id or self.payment.id}/confirm/",
            {"payload": payload or {}},
            format="json",
        )

    def test_anonymous_is_rejected(self):
        self.assertEqual(
            self._post().status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_manager_is_rejected(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self._post().status_code, status.HTTP_403_FORBIDDEN
        )

    def test_foreign_payment_is_a_404(self):
        self.client.force_authenticate(self.other)
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"], "PAYMENT_NOT_FOUND")

    def test_unknown_payment_is_a_404(self):
        self.client.force_authenticate(self.consumer)
        self.assertEqual(
            self._post(payment_id=999999).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_success_confirms_payment_and_booking(self):
        self.client.force_authenticate(self.consumer)
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Payment.Status.SUCCEEDED)
        self.assertTrue(response.data["booking_applied"])
        self.assertIsNotNone(response.data["paid_at"])

        self.payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertTrue(self.payment.booking_applied)
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)
        self.assertIsNone(self.booking.hold_expires_at)

    def test_declined_callback_fails_the_payment(self):
        self.client.force_authenticate(self.consumer)
        response = self._post(payload={"outcome": "failure"})
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"], "PAYMENT_VERIFICATION_FAILED")
        self.payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.FAILED)
        self.assertEqual(self.booking.status, Booking.Status.PENDING_PAYMENT)

    def test_captured_but_not_applied_keeps_the_money_row(self):
        # Hold lapses before the callback arrives: the money is captured, the
        # booking can no longer be confirmed. Payment stays SUCCEEDED and is
        # flagged not-applied; the refund is 5.5 (D60).
        self.booking.hold_expires_at = timezone.now() - timedelta(minutes=1)
        self.booking.save(update_fields=["hold_expires_at"])
        self.client.force_authenticate(self.consumer)
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["error"], "PAYMENT_CAPTURED_NOT_APPLIED"
        )
        self.payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertFalse(self.payment.booking_applied)
        self.assertTrue(
            self.payment.failure_reason.startswith("booking_not_confirmable")
        )
        self.assertEqual(self.booking.status, Booking.Status.PENDING_PAYMENT)

    def test_repeat_confirm_is_idempotent(self):
        self.client.force_authenticate(self.consumer)
        first = self._post()
        second = self._post()
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(self.booking.payments.count(), 1)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_cash_payment_is_not_confirmable(self):
        cash = Payment.objects.create(
            booking=self.booking, amount=Decimal("40.00"),
            method=Payment.Method.CASH,
        )
        self.client.force_authenticate(self.consumer)
        response = self._post(payment_id=cash.id)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"], "PAYMENT_NOT_CONFIRMABLE")

    @override_settings(PAYMENT_GATEWAY="razorpay")
    def test_gateway_unavailable_is_a_503(self):
        self.client.force_authenticate(self.consumer)
        response = self._post()
        self.assertEqual(
            response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE
        )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)


class PaymentWebhookApiTests(TestCase):
    """``POST /api/payments/webhook/`` (increment 5.4, D60)."""

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
            email="consumer@example.com", password="Tr0ub4dor&3",
            full_name="Consumer",
        )

    def setUp(self):
        self.client = APIClient()
        now = timezone.now()
        self.booking = Booking.objects.create(
            user=self.consumer, created_by=self.consumer, vehicle=None,
            vehicle_plate="KA01AB1234", slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            billed_hours=2, hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
            status=Booking.Status.PENDING_PAYMENT,
            hold_expires_at=now + timedelta(minutes=5),
        )
        self.payment = Payment.objects.create(
            booking=self.booking, amount=Decimal("40.00"),
            provider_order_id="order_wh_1",
        )

    def _body(self, event="payment.captured", order_id="order_wh_1", payment_id="pay_wh_1"):
        return json.dumps(
            {
                "event": event,
                "payload": {
                    "payment": {
                        "entity": {"id": payment_id, "order_id": order_id}
                    }
                },
            }
        )

    def _post(self, body, signed=True):
        headers = (
            {MOCK_WEBHOOK_HEADER: MOCK_WEBHOOK_SIGNATURE} if signed else {}
        )
        return self.client.post(
            "/api/payments/webhook/",
            data=body,
            content_type="application/json",
            headers=headers,
        )

    def test_unsigned_webhook_is_a_400(self):
        response = self._post(self._body(), signed=False)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "INVALID_WEBHOOK_SIGNATURE")

    def test_captured_webhook_confirms(self):
        response = self._post(self._body())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.payment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.payment.provider_payment_id, "pay_wh_1")
        self.assertTrue(self.payment.booking_applied)
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_failed_webhook_marks_payment_failed(self):
        response = self._post(self._body("payment.failed"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.FAILED)

    def test_unknown_order_is_acknowledged(self):
        response = self._post(
            self._body(order_id="order_nope", payment_id="pay_nope")
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    def test_duplicate_webhook_is_idempotent(self):
        self._post(self._body())
        second = self._post(self._body())
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(self.booking.payments.count(), 1)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_webhook_is_public(self):
        # No force_authenticate: signature, not JWT, is the authentication.
        response = self._post(self._body())
        self.assertNotIn(response.status_code, (401, 403))

class RefundLedgerModelTests(TestCase):
    """The Refund model (5.5, D61)."""

    @classmethod
    def setUpTestData(cls):
        City.objects.all().delete()
        city = City.objects.create(code="BLR", name="Bengaluru")
        lot = ParkingLot.objects.create(
            city=city, number=1, name="MG Road", address_line="1 MG Road",
        )
        slot = ParkingSlot.objects.create(
            lot=lot, number="A-01", slot_type=ParkingSlot.SlotType.REGULAR,
        )
        user = User.objects.create_user(
            email="consumer@example.com", password="Tr0ub4dor&3",
            full_name="Consumer",
        )
        now = timezone.now()
        cls.booking = Booking.objects.create(
            user=user, created_by=user, vehicle=None, vehicle_plate="KA01AB1234",
            slot=slot, slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=3),
            billed_hours=2, hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
        )
        cls.payment = Payment.objects.create(
            booking=cls.booking, amount=Decimal("40.00"),
        )

    def test_defaults(self):
        refund = Refund.objects.create(
            payment=self.payment, amount=Decimal("40.00"),
        )
        self.assertEqual(refund.status, Refund.Status.PENDING)
        self.assertIsNone(refund.provider_refund_id)

    def test_amount_must_be_positive(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Refund.objects.create(
                    payment=self.payment, amount=Decimal("0.00"),
                )

    def test_blank_provider_id_becomes_null(self):
        refund = Refund.objects.create(
            payment=self.payment, amount=Decimal("10.00"),
            provider_refund_id="",
        )
        refund.refresh_from_db()
        self.assertIsNone(refund.provider_refund_id)

    def test_payment_with_refund_cannot_be_deleted(self):
        Refund.objects.create(
            payment=self.payment, amount=Decimal("10.00"),
        )
        with self.assertRaises(ProtectedError):
            self.payment.delete()


class PaymentRefundApiTests(TestCase):
    """``POST /api/payments/{id}/refund/`` (5.5, D61)."""

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
            email="consumer@example.com", password="Tr0ub4dor&3",
            full_name="Consumer",
        )
        cls.manager = User.objects.create_user(
            email="manager@example.com", password="Tr0ub4dor&3",
            full_name="Manager", role=User.Role.MANAGER,
        )
        cls.admin = User.objects.create_user(
            email="admin@example.com", password="Tr0ub4dor&3",
            full_name="Admin", role=User.Role.ADMIN,
        )

    def setUp(self):
        self.client = APIClient()
        now = timezone.now()
        self.booking = Booking.objects.create(
            user=self.consumer, created_by=self.consumer, vehicle=None,
            vehicle_plate="KA01AB1234", slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=3),
            end_time=now + timedelta(hours=5),
            billed_hours=2, hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
            status=Booking.Status.CONFIRMED,
        )
        self.payment = Payment.objects.create(
            booking=self.booking, amount=Decimal("40.00"),
            status=Payment.Status.SUCCEEDED,
            provider_order_id="order_ref_1",
            provider_payment_id="pay_ref_1",
            booking_applied=True,
            paid_at=now,
        )

    def _cancel(self):
        # Simulate what Phase 4 stores at cancellation (D53).
        self.booking.status = Booking.Status.CANCELLED
        self.booking.refund_due_amount = Decimal("40.00")
        self.booking.save(update_fields=["status", "refund_due_amount"])

    def _refund(self, payment_id=None):
        return self.client.post(
            f"/api/payments/{payment_id or self.payment.id}/refund/"
        )

    def test_anonymous_is_rejected(self):
        self.assertEqual(self._refund().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_consumer_is_rejected(self):
        self.client.force_authenticate(self.consumer)
        self.assertEqual(self._refund().status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_refunds_the_cancelled_booking_charge(self):
        self._cancel()
        self.client.force_authenticate(self.manager)
        response = self._refund()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Refund.Status.SUCCEEDED)
        self.assertEqual(Decimal(response.data["amount"]), Decimal("40.00"))
        self.assertTrue(response.data["provider_refund_id"].startswith("rfnd_mock_"))

        # D61: the captured payment is NOT mutated.
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)
        self.assertEqual(self.payment.refunds.count(), 1)

    def test_non_cancelled_booking_is_not_refundable(self):
        self.client.force_authenticate(self.admin)
        response = self._refund()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"], "PAYMENT_NOT_REFUNDABLE")
        self.assertEqual(self.payment.refunds.count(), 0)

    def test_captured_not_applied_is_refundable(self):
        # D60: money captured, booking never applied -> full capture owed.
        self.payment.booking_applied = False
        self.payment.save(update_fields=["booking_applied"])
        self.booking.status = Booking.Status.PENDING_PAYMENT
        self.booking.save(update_fields=["status"])
        self.client.force_authenticate(self.admin)
        response = self._refund()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(response.data["amount"]), Decimal("40.00"))

    def test_repeat_refund_is_idempotent(self):
        self._cancel()
        self.client.force_authenticate(self.manager)
        first = self._refund()
        second = self._refund()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(self.payment.refunds.count(), 1)

    def test_failed_payment_is_not_refundable(self):
        self._cancel()
        self.payment.status = Payment.Status.FAILED
        self.payment.save(update_fields=["status"])
        self.client.force_authenticate(self.manager)
        response = self._refund()
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_unknown_payment_is_a_404(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(
            self._refund(payment_id=999999).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    @patch("apps.payments.services.get_payment_gateway")
    def test_gateway_failure_is_recorded_and_retriable(self, get_gateway):
        class FailingRefundGateway(MockGateway):
            def refund_payment(self, *, gateway_payment_id, amount):
                raise PaymentGatewayError("refund endpoint down")

        self._cancel()
        self.client.force_authenticate(self.manager)

        get_gateway.return_value = FailingRefundGateway()
        response = self._refund()
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["error"], "PAYMENT_REFUND_FAILED")
        self.assertEqual(
            self.payment.refunds.get().status, Refund.Status.FAILED
        )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)

        # A retry with a working gateway settles a fresh attempt.
        get_gateway.return_value = MockGateway()
        retry = self._refund()
        self.assertEqual(retry.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            self.payment.refunds.filter(status=Refund.Status.SUCCEEDED).count(), 1
        )
        self.assertEqual(self.payment.refunds.count(), 2)


class CancellationAutoRefundTests(TestCase):
    """Cancelling a paid booking triggers the D61 refund automatically (5.5)."""

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
            email="consumer@example.com", password="Tr0ub4dor&3",
            full_name="Consumer",
        )

    def setUp(self):
        self.client = APIClient()
        now = timezone.now()
        self.booking = Booking.objects.create(
            user=self.consumer, created_by=self.consumer, vehicle=None,
            vehicle_plate="KA01AB1234", slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=now + timedelta(hours=3),
            end_time=now + timedelta(hours=5),
            billed_hours=2, hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
            status=Booking.Status.CONFIRMED,
        )
        self.payment = Payment.objects.create(
            booking=self.booking, amount=Decimal("40.00"),
            status=Payment.Status.SUCCEEDED,
            provider_order_id="order_auto_1",
            provider_payment_id="pay_auto_1",
            booking_applied=True,
            paid_at=now,
        )

    def _cancel(self):
        return self.client.post(f"/api/bookings/{self.booking.id}/cancel/")

    def test_cancelling_refunds_the_paid_amount(self):
        self.client.force_authenticate(self.consumer)
        response = self._cancel()
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)
        self.assertEqual(self.booking.refund_due_amount, Decimal("40.00"))

        refund = self.payment.refunds.get()
        self.assertEqual(refund.status, Refund.Status.SUCCEEDED)
        self.assertEqual(refund.amount, Decimal("40.00"))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.SUCCEEDED)

    def test_cancelling_inside_the_cutoff_moves_no_money(self):
        # Inside the 30-minute window (§19): nothing is owed, nothing moves.
        self.booking.start_time = timezone.now() + timedelta(minutes=5)
        self.booking.save(update_fields=["start_time"])
        self.client.force_authenticate(self.consumer)
        response = self._cancel()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.refund_due_amount, Decimal("0.00"))
        self.assertEqual(self.payment.refunds.count(), 0)


class PaymentExtensionApiTests(TestCase):
    """Extension charge via POST /api/payments/ (increment 5.6, D62)."""

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
            email="consumer@example.com", password="Tr0ub4dor&3",
            full_name="Consumer",
        )
        cls.other = User.objects.create_user(
            email="other@example.com", password="Tr0ub4dor&3",
            full_name="Other",
        )

    def setUp(self):
        self.client = APIClient()
        self.now = timezone.now()
        # A paid, extendable booking: 2 hours starting in an hour, ends +3h.
        self.booking = Booking.objects.create(
            user=self.consumer, created_by=self.consumer, vehicle=None,
            vehicle_plate="KA01AB1234", slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=self.now + timedelta(hours=1),
            end_time=self.now + timedelta(hours=3),
            billed_hours=2, hourly_rate=Decimal("20.00"),
            base_amount=Decimal("40.00"),
            status=Booking.Status.CONFIRMED, hold_expires_at=None,
        )
        # The extension target: +5h, i.e. 2 added hours = 40.00.
        self.new_end = self.now + timedelta(hours=5)

    def _post(self, payload):
        return self.client.post("/api/payments/", payload, format="json")

    def _extension_payload(self):
        return {
            "booking": self.booking.id,
            "purpose": Payment.Purpose.EXTENSION,
            "end_time": self.new_end.isoformat(),
        }

    def test_consumer_starts_an_extension_payment(self):
        self.client.force_authenticate(self.consumer)
        response = self._post(self._extension_payload())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["purpose"], Payment.Purpose.EXTENSION)
        self.assertEqual(Decimal(response.data["amount"]), Decimal("40.00"))
        self.assertIsNotNone(response.data["extension_end_time"])

        payment = Payment.objects.get(pk=response.data["id"])
        self.assertEqual(payment.extension_end_time, self.new_end)

    def test_extension_requires_an_end_time(self):
        self.client.force_authenticate(self.consumer)
        response = self._post(
            {"booking": self.booking.id, "purpose": Payment.Purpose.EXTENSION}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_booking_purpose_rejects_an_end_time(self):
        self.client.force_authenticate(self.consumer)
        response = self._post(
            {"booking": self.booking.id, "end_time": self.new_end.isoformat()}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unpaid_booking_cannot_be_extended(self):
        self.booking.status = Booking.Status.PENDING_PAYMENT
        self.booking.save(update_fields=["status"])
        self.client.force_authenticate(self.consumer)
        response = self._post(self._extension_payload())
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"], "BOOKING_NOT_EXTENDABLE")

    def test_end_time_must_lengthen_the_booking(self):
        self.client.force_authenticate(self.consumer)
        payload = self._extension_payload()
        payload["end_time"] = (self.now + timedelta(hours=2)).isoformat()
        response = self._post(payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "INVALID_EXTENSION")

    def test_confirmation_applies_the_extension(self):
        self.client.force_authenticate(self.consumer)
        started = self._post(self._extension_payload())
        payment_id = started.data["id"]

        response = self.client.post(
            f"/api/payments/{payment_id}/confirm/", {"payload": {}}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Payment.Status.SUCCEEDED)
        self.assertTrue(response.data["booking_applied"])

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.end_time, self.new_end)
        self.assertEqual(self.booking.billed_hours, 4)
        self.assertEqual(self.booking.base_amount, Decimal("80.00"))

    def test_taken_slot_is_captured_not_applied(self):
        # A competing confirmed booking takes the added window after the
        # extension payment is started but before it is confirmed.
        Booking.objects.create(
            user=self.other, created_by=self.other, vehicle=None,
            vehicle_plate="KA01XY9999", slot=self.slot,
            slot_type=ParkingSlot.SlotType.REGULAR,
            start_time=self.now + timedelta(hours=3),
            end_time=self.now + timedelta(hours=4),
            billed_hours=1, hourly_rate=Decimal("20.00"),
            base_amount=Decimal("20.00"),
            status=Booking.Status.CONFIRMED, hold_expires_at=None,
        )
        self.client.force_authenticate(self.consumer)
        started = self._post(self._extension_payload())
        response = self.client.post(
            f"/api/payments/{started.data['id']}/confirm/",
            {"payload": {}}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["error"], "PAYMENT_CAPTURED_NOT_APPLIED"
        )

        payment = Payment.objects.get(pk=started.data["id"])
        self.assertEqual(payment.status, Payment.Status.SUCCEEDED)
        self.assertFalse(payment.booking_applied)
        self.assertTrue(payment.failure_reason.startswith("booking_not_applied"))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.end_time, self.now + timedelta(hours=3))

    def test_duplicate_extension_is_refused(self):
        self.client.force_authenticate(self.consumer)
        started = self._post(self._extension_payload())
        self.client.post(
            f"/api/payments/{started.data['id']}/confirm/", {"payload": {}},
            format="json",
        )
        response = self._post(self._extension_payload())
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"], "EXTENSION_ALREADY_PAID")