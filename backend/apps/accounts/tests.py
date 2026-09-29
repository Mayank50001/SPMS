"""Tests for the accounts domain.

Automated testing is incremental rather than deferred to Phase 10 (PROJECT.md
§34 puts authorization rules explicitly in unit-test scope). Earlier the role
permission classes had no consumer endpoint to run through, so the permission
tests had to inject them into a throwaway view; the vehicle API now exercises
``IsConsumer`` for real as well.

These tests deliberately route through DRF's real view machinery instead of
calling ``has_permission()`` directly. The behaviour worth testing -- DRF
choosing 401 vs 403 -- happens inside ``APIView.initial`` and is invisible from
a direct method call.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, Vehicle
from .permissions import IsAdmin, IsConsumer, IsManager
from .serializers import RegisterSerializer


class _RoleGatedView(APIView):
    """Minimal view used only to exercise a permission through DRF.

    Its only purpose is to give the permission classes something to run inside,
    so the tests can assert on HTTP status codes. The permission under test is
    injected per call via ``as_view(permission_classes=[...])``.
    """

    def get(self, request):
        return Response({"ok": True})


class RolePermissionTests(TestCase):
    """Authorization matrix for apps.accounts.permissions."""

    @classmethod
    def setUpTestData(cls):
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
        cls.admin = User.objects.create_user(
            email="admin@example.com",
            password="Tr0ub4dor&3",
            full_name="Admin",
            role=User.Role.ADMIN,
        )

    def setUp(self):
        self.factory = APIRequestFactory()

    def _call(self, permission_classes, user=None):
        """Run _RoleGatedView with the given permissions as ``user``.

        With ``user=None`` no Authorization header is sent, so this exercises the
        genuinely unauthenticated path.
        """
        view = _RoleGatedView.as_view(permission_classes=permission_classes)
        extra = {}
        if user is not None:
            # A real signed token, so JWTAuthentication runs for real rather than
            # being stubbed out.
            token = RefreshToken.for_user(user).access_token
            extra["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        return view(self.factory.get("/role-gated/", **extra))

    def test_anonymous_request_is_not_authenticated(self):
        """No credentials -> 401 on every role permission, never 403."""
        for permission in (IsConsumer, IsManager, IsAdmin):
            with self.subTest(permission=permission.__name__):
                response = self._call([permission])
                self.assertEqual(
                    response.status_code, status.HTTP_401_UNAUTHORIZED
                )

    def test_role_matrix(self):
        """Only the matching role is allowed; every other role gets 403."""
        cases = (
            (IsConsumer, "consumer", status.HTTP_200_OK),
            (IsConsumer, "manager", status.HTTP_403_FORBIDDEN),
            (IsConsumer, "admin", status.HTTP_403_FORBIDDEN),
            (IsManager, "consumer", status.HTTP_403_FORBIDDEN),
            (IsManager, "manager", status.HTTP_200_OK),
            (IsManager, "admin", status.HTTP_403_FORBIDDEN),
            (IsAdmin, "consumer", status.HTTP_403_FORBIDDEN),
            (IsAdmin, "manager", status.HTTP_403_FORBIDDEN),
            (IsAdmin, "admin", status.HTTP_200_OK),
        )
        for permission, role, expected in cases:
            user = getattr(self, role)
            with self.subTest(permission=permission.__name__, as_role=role):
                response = self._call([permission], user=user)
                self.assertEqual(response.status_code, expected)

    def test_wrong_role_reports_which_role_is_required(self):
        """The 403 body names the required role, so the frontend can explain it."""
        response = self._call([IsManager], user=self.consumer)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["detail"],
            "This endpoint is available to parking managers only.",
        )

    def test_suspended_user_is_rejected_though_the_token_is_still_valid(self):
        """Suspension takes effect immediately, with no token refresh (D15).

        The token is minted BEFORE the suspension, so it is cryptographically
        valid and unexpired at the moment it is presented.
        """
        token = RefreshToken.for_user(self.manager).access_token
        User.objects.filter(pk=self.manager.pk).update(is_active=False)

        request = self.factory.get(
            "/role-gated/", HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        response = _RoleGatedView.as_view(permission_classes=[IsManager])(request)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_is_superuser_alone_does_not_satisfy_is_admin(self):
        """IsAdmin is role-based only -- a superuser still needs role=ADMIN.

        Model-level superuser flags grant Django admin access, not API access.
        """
        superuser = User.objects.create_user(
            email="super@example.com",
            password="Tr0ub4dor&3",
            full_name="Super",
            is_superuser=True,
        )
        self.assertEqual(superuser.role, User.Role.CONSUMER)

        response = self._call([IsAdmin], user=superuser)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class RegisterSerializerTests(TestCase):
    """B2: a password or its hash must never appear in a response body."""

    def test_registration_response_omits_both_password_fields(self):
        response = APIClient().post(
            "/api/auth/register/",
            {
                "email": "newconsumer@example.com",
                "full_name": "New Consumer",
                "password": "Tr0ub4dor&3",
                "password_confirm": "Tr0ub4dor&3",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", response.data)
        self.assertNotIn("password_confirm", response.data)
        self.assertNotIn("pbkdf2", str(response.data))

    def test_serialising_an_existing_user_omits_the_hash(self):
        user = User.objects.create_user(
            email="readback@example.com",
            password="Tr0ub4dor&3",
            full_name="Read Back",
        )

        data = RegisterSerializer(user).data

        self.assertNotIn("password", data)
        self.assertNotIn("password_confirm", data)
        self.assertNotIn("pbkdf2", str(data))


class EmailNormalisationTests(TestCase):
    """B3 + case-insensitive login (D13).

    The two halves must agree: ``User.save()`` lower-cases what is stored, and
    ``UserManager.get_by_natural_key`` lower-cases what is looked up. Testing
    them together is what proves a mixed-case registration still logs in.
    """

    def test_save_stores_a_stripped_lower_case_email(self):
        user = User.objects.create_user(
            email="  MixedCase@Example.COM ",
            password="Tr0ub4dor&3",
            full_name="Mixed Case",
        )

        user.refresh_from_db()
        self.assertEqual(user.email, "mixedcase@example.com")

    def test_login_accepts_any_case_variant_of_the_email(self):
        User.objects.create_user(
            email="MixedCase@Example.COM",
            password="Tr0ub4dor&3",
            full_name="Mixed Case",
        )
        client = APIClient()

        for attempt in (
            "mixedcase@example.com",
            "MixedCase@Example.com",
            "MIXEDCASE@EXAMPLE.COM",
        ):
            with self.subTest(email=attempt):
                response = client.post(
                    "/api/auth/login/",
                    {"email": attempt, "password": "Tr0ub4dor&3"},
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertIn("access", response.data)

class PasswordSimilarityTest(TestCase):
    """B4: the similarity validator must compare against ``full_name`` too.

    The stock attribute list is ('username', 'first_name', 'last_name',
    'email'); this model has none of the first three, so ``full_name`` was
    silently skipped. settings.AUTH_PASSWORD_VALIDATORS now passes
    ``user_attributes=("email", "full_name")``.

    The example name is deliberately absent from Django's common-password list
    and longer than the 8-character minimum, so a rejection can only come from
    the similarity check -- not from a different validator.
    """

    def _register(self, password):
        return APIClient().post(
            "/api/auth/register/",
            {
                "email" : "khadayatemayank9595@gmail.com",
                "full_name" : "Khadayate Mayank",
                "password" : password,
                "password_confirm" : password,
            },
            format="json",
        )

    def test_password_equal_to_email_is_rejected(self):
        response = self._register("Mayank@123")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_unrelated_strong_password_is_accepted(self):
        response = self._register("correct-horse-battery-staple")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

class PhoneFieldTests(TestCase):
    """D23: phone is optional, digits-only and non-unique."""

    def _register(self, phone=None, email="phonetest@example.com"):
        payload = {
            "email" : email,
            "full_name" : "Phone Tester",
            "password" : "correct-horse-battery-staple",
            "password_confirm" : "correct-horse-battery-staple",
        }
        if phone is not None:
            payload["phone"] = phone

        return APIClient().post("/api/auth/register/", payload, format="json")

    def test_duplicate_phone_is_allowed(self):
        first = self._register("9876543210", email="first@example.com")
        second = self._register("9876543210", email="second@example.com")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)

    def test_phone_with_letters_is_rejected(self):
        response = self._register("call-me-maybe")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)

    def test_too_short_phone_is_rejected(self):
        response = self._register("123")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)

    def test_blank_phone_is_stored_as_none(self):
        response = self._register("")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(
            User.objects.get(email="phonetest@example.com").phone
        )

    def test_phone_may_be_omitted(self):
        response = self._register(None)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(
            User.objects.get(email="phonetest@example.com").phone
        )

    def test_formatted_phone_is_stored_as_digits(self):
        response = self._register("+91 98765-43210")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            User.objects.get(email="phonetest@example.com").phone,
            "919876543210",
        )

class ProfileUpdateTests(TestCase):
    """PATCH /api/auth/me/ updates only the caller's own profile."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="profile@example.com",
            password="correct-horse-battery-staple",
            full_name="Original Name",
            phone="9876543210",
        )

    def setUp(self):
        self.client = APIClient()
        token = RefreshToken.for_user(self.user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_patch_updates_name_and_normalises_phone(self):
        response = self.client.patch(
            "/api/auth/me/",
            {"full_name": "Updated Name", "phone": "+91 90000-11111"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Updated Name")
        self.assertEqual(self.user.phone, "919000011111")
        # The response is the full read shape, matching GET.
        self.assertEqual(response.data["full_name"], "Updated Name")
        self.assertIn("role", response.data)

    def test_patch_cannot_change_email_or_role(self):
        response = self.client.patch(
            "/api/auth/me/",
            {"email": "hacker@example.com", "role": "ADMIN"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "profile@example.com")
        self.assertEqual(self.user.role, User.Role.CONSUMER)

    def test_phone_can_be_cleared(self):
        response = self.client.patch(
            "/api/auth/me/", {"phone": ""}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone)

    def test_blank_full_name_is_rejected(self):
        response = self.client.patch(
            "/api/auth/me/", {"full_name": "   "}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("full_name", response.data)

    def test_patch_requires_authentication(self):
        self.client.credentials()
        response = self.client.patch(
            "/api/auth/me/", {"full_name": "Nope"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_put_is_not_allowed(self):
        response = self.client.put(
            "/api/auth/me/", {"full_name": "Nope"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

class AdminUserManagementTests(TestCase):
    """D20: only Administrators create or list privileged accounts."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            email="admin@example.com",
            password="correct-horse-battery-staple",
            full_name="Admin",
            role=User.Role.ADMIN,
        )
        cls.manager = User.objects.create_user(
            email="manager@example.com",
            password="correct-horse-battery-staple",
            full_name="Manager",
            role=User.Role.MANAGER,
        )
        cls.consumer = User.objects.create_user(
            email="consumer@example.com",
            password="correct-horse-battery-staple",
            full_name="Consumer",
        )

    def setUp(self):
        self.client = APIClient()

    def _authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _create_payload(self, **overrides):
        payload = {
            "email": "newmanager@example.com",
            "full_name": "New Manager",
            "role": "MANAGER",
            "password": "correct-horse-battery-staple",
        }
        payload.update(overrides)
        return payload

    def test_admin_can_create_a_manager(self):
        self._authenticate(self.admin)
        response = self.client.post(
            "/api/users/", self._create_payload(), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["role"], "MANAGER")
        self.assertNotIn("password", response.data)
        created = User.objects.get(email="newmanager@example.com")
        self.assertTrue(created.check_password("correct-horse-battery-staple"))

    def test_admin_can_create_another_admin(self):
        self._authenticate(self.admin)
        response = self.client.post(
            "/api/users/",
            self._create_payload(email="admin2@example.com", role="ADMIN"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = User.objects.get(email="admin2@example.com")
        self.assertEqual(created.role, User.Role.ADMIN)
        # API authority only -- not Django-admin access.
        self.assertFalse(created.is_staff)

    def test_consumer_role_cannot_be_created_here(self):
        self._authenticate(self.admin)
        response = self.client.post(
            "/api/users/",
            self._create_payload(role="CONSUMER"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)

    def test_weak_password_is_rejected(self):
        self._authenticate(self.admin)
        response = self.client.post(
            "/api/users/", self._create_payload(password="123"), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_duplicate_email_is_rejected_case_insensitively(self):
        self._authenticate(self.admin)
        response = self.client.post(
            "/api/users/",
            self._create_payload(email="Admin@Example.com"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_non_admin_cannot_create(self):
        for actor in (self.manager, self.consumer):
            with self.subTest(actor=actor.role):
                self._authenticate(actor)
                response = self.client.post(
                    "/api/users/", self._create_payload(), format="json"
                )
                self.assertEqual(
                    response.status_code, status.HTTP_403_FORBIDDEN
                )

    def test_anonymous_cannot_list(self):
        response = self.client.get("/api/users/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_list_and_filter_users(self):
        self._authenticate(self.admin)

        response = self.client.get("/api/users/", {"role": "ADMIN"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        emails = [row["email"] for row in response.data]
        self.assertIn("admin@example.com", emails)
        self.assertNotIn("consumer@example.com", emails)

    def test_admin_can_retrieve_a_user(self):
        self._authenticate(self.admin)

        response = self.client.get(f"/api/users/{self.consumer.pk}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "consumer@example.com")
        self.assertNotIn("password", response.data)

    def test_consumer_cannot_retrieve_a_user(self):
        self._authenticate(self.consumer)

        response = self.client.get(f"/api/users/{self.admin.pk}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class UserAccessUpdateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            email="admin@example.com",
            password="correct-horse-battery-staple",
            full_name="Admin",
            role=User.Role.ADMIN,
        )
        cls.manager = User.objects.create_user(
            email="manager@example.com",
            password="correct-horse-battery-staple",
            full_name="Manager",
            role=User.Role.MANAGER,
        )
        cls.consumer = User.objects.create_user(
            email="consumer@example.com",
            password="correct-horse-battery-staple",
            full_name="Consumer",
        )

    def setUp(self):
        self.client = APIClient()

    def _authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _patch(self, user_id, **payload):
        return self.client.patch(f"/api/users/{user_id}/", payload, format="json")

    def _make_second_admin(self):
        return User.objects.create_user(
            email="admin2@example.com",
            password="correct-horse-battery-staple",
            full_name="Admin Two",
            role=User.Role.ADMIN,
        )

    def test_admin_can_change_a_consumer_to_manager(self):
        self._authenticate(self.admin)

        response = self._patch(self.consumer.pk, role="MANAGER")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("password", response.data)
        self.assertIn("created_at", response.data)
        self.consumer.refresh_from_db()
        self.assertEqual(self.consumer.role, User.Role.MANAGER)

    def test_admin_can_suspend_and_reactivate_an_account(self):
        self._authenticate(self.admin)

        suspended = self._patch(self.consumer.pk, is_active=False)
        self.assertEqual(suspended.status_code, status.HTTP_200_OK)
        self.consumer.refresh_from_db()
        self.assertFalse(self.consumer.is_active)

        restored = self._patch(self.consumer.pk, is_active=True)
        self.assertEqual(restored.status_code, status.HTTP_200_OK)
        self.consumer.refresh_from_db()
        self.assertTrue(self.consumer.is_active)

    def test_cannot_demote_the_last_active_administrator(self):
        self._authenticate(self.admin)

        response = self._patch(self.admin.pk, role="MANAGER")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"], "LAST_ADMINISTRATOR")
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, User.Role.ADMIN)

    def test_cannot_suspend_the_last_active_administrator(self):
        self._authenticate(self.admin)

        response = self._patch(self.admin.pk, is_active=False)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_can_demote_themselves_when_another_admin_remains(self):
        second = self._make_second_admin()
        self._authenticate(second)

        response = self._patch(self.admin.pk, role="CONSUMER")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, User.Role.CONSUMER)

    def test_suspension_takes_effect_on_the_next_request(self):
        manager_token = RefreshToken.for_user(self.manager).access_token
        self._authenticate(self.admin)
        self._patch(self.manager.pk, is_active=False)

        fresh = APIClient()
        fresh.credentials(HTTP_AUTHORIZATION=f"Bearer {manager_token}")
        response = fresh.get("/api/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_admin_cannot_change_access(self):
        for actor in (self.manager, self.consumer):
            with self.subTest(actor=actor.role):
                self._authenticate(actor)
                response = self._patch(self.consumer.pk, role="MANAGER")
                self.assertEqual(
                    response.status_code, status.HTTP_403_FORBIDDEN
                )

    def test_invalid_role_is_rejected(self):
        self._authenticate(self.admin)

        response = self._patch(self.consumer.pk, role="SUPERUSER")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)

    def test_empty_payload_is_rejected(self):
        self._authenticate(self.admin)

        response = self.client.patch(
            f"/api/users/{self.consumer.pk}/", {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_anonymous_cannot_change_access(self):
        response = self._patch(self.consumer.pk, role="MANAGER")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_put_is_not_allowed(self):
        self._authenticate(self.admin)

        response = self.client.put(
            f"/api/users/{self.consumer.pk}/",
            {"role": "MANAGER"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class VehicleModelTests(TestCase):
    """Unit tests for the canonical plate format (V2)."""

    def test_segments_round_trip_through_the_canonical_form(self):
        number = Vehicle.build_registration_number(
            state_code="ka", rto_code="01", series="ab", unique_number="1234"
        )

        self.assertEqual(number, "KA01AB1234")

        vehicle = Vehicle(registration_number=number)
        self.assertEqual(vehicle.state_code, "KA")
        self.assertEqual(vehicle.rto_code, "01")
        self.assertEqual(vehicle.series, "AB")
        self.assertEqual(vehicle.unique_number, "1234")


class VehicleApiTests(TestCase):
    """Consumer vehicle CRUD, ownership scoping and plate validation."""

    @classmethod
    def setUpTestData(cls):
        cls.consumer = User.objects.create_user(
            email="owner@example.com",
            password="correct-horse-battery-staple",
            full_name="Owner",
        )
        cls.other = User.objects.create_user(
            email="other@example.com",
            password="correct-horse-battery-staple",
            full_name="Other",
        )
        cls.manager = User.objects.create_user(
            email="vehicle-manager@example.com",
            password="correct-horse-battery-staple",
            full_name="Manager",
            role=User.Role.MANAGER,
        )
        cls.admin = User.objects.create_user(
            email="vehicle-admin@example.com",
            password="correct-horse-battery-staple",
            full_name="Admin",
            role=User.Role.ADMIN,
        )

    def setUp(self):
        self.client = APIClient()
        self._authenticate(self.consumer)

    def _authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _payload(self, **overrides):
        data = {
            "state_code": "KA",
            "rto_code": "01",
            "series": "AB",
            "unique_number": "1234",
            "make": "Maruti",
            "model": "Swift",
            "color": "White",
        }
        data.update(overrides)
        return data

    def test_consumer_can_register_a_vehicle(self):
        response = self.client.post("/api/vehicles/", self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["registration_number"], "KA01AB1234")
        # The read shape echoes the four segments back for the UI.
        self.assertEqual(response.data["state_code"], "KA")
        self.assertEqual(response.data["unique_number"], "1234")
        self.assertEqual(response.data["make"], "Maruti")

        vehicle = Vehicle.objects.get()
        self.assertEqual(vehicle.owner, self.consumer)

    def test_segments_are_case_insensitive_in_but_stored_upper_case(self):
        response = self.client.post(
            "/api/vehicles/",
            self._payload(state_code="ka", series="ab"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["registration_number"], "KA01AB1234")

    def test_all_four_segments_are_required(self):
        response = self.client.post(
            "/api/vehicles/", {"make": "Maruti"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for field in ("state_code", "rto_code", "series", "unique_number"):
            self.assertIn(field, response.data)

    def test_unknown_state_code_is_rejected(self):
        response = self.client.post(
            "/api/vehicles/", self._payload(state_code="ZZ"), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("state_code", response.data)

    def test_rto_code_must_be_two_digits(self):
        response = self.client.post(
            "/api/vehicles/", self._payload(rto_code="1"), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("rto_code", response.data)

    def test_series_must_be_two_letters(self):
        response = self.client.post(
            "/api/vehicles/", self._payload(series="12"), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("series", response.data)

    def test_unique_number_must_be_four_digits(self):
        response = self.client.post(
            "/api/vehicles/", self._payload(unique_number="123"), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unique_number", response.data)

    def test_plate_is_globally_unique_across_owners(self):
        Vehicle.objects.create(owner=self.other, registration_number="KA01AB1234")

        response = self.client.post("/api/vehicles/", self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("registration_number", response.data)

    def test_list_returns_only_the_callers_own_vehicles(self):
        mine = Vehicle.objects.create(
            owner=self.consumer, registration_number="KA01AB1234"
        )
        Vehicle.objects.create(owner=self.other, registration_number="MH12XY9999")

        response = self.client.get("/api/vehicles/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], mine.pk)

    def test_cannot_retrieve_another_consumers_vehicle(self):
        theirs = Vehicle.objects.create(
            owner=self.other, registration_number="MH12XY9999"
        )

        response = self.client.get(f"/api/vehicles/{theirs.pk}/")

        # 404, not 403: the scoped queryset must not reveal that it exists.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_metadata_without_touching_the_plate(self):
        mine = Vehicle.objects.create(
            owner=self.consumer, registration_number="KA01AB1234"
        )

        response = self.client.patch(
            f"/api/vehicles/{mine.pk}/", {"color": "Black"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["color"], "Black")
        self.assertEqual(response.data["registration_number"], "KA01AB1234")

    def test_patch_with_a_partial_segment_set_is_rejected(self):
        mine = Vehicle.objects.create(
            owner=self.consumer, registration_number="KA01AB1234"
        )

        response = self.client.patch(
            f"/api/vehicles/{mine.pk}/", {"state_code": "MH"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_with_all_segments_updates_the_plate(self):
        mine = Vehicle.objects.create(
            owner=self.consumer, registration_number="KA01AB1234"
        )

        response = self.client.patch(
            f"/api/vehicles/{mine.pk}/",
            {
                "state_code": "MH",
                "rto_code": "12",
                "series": "XY",
                "unique_number": "9999",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mine.refresh_from_db()
        self.assertEqual(mine.registration_number, "MH12XY9999")

    def test_patch_plate_onto_an_existing_plate_is_rejected(self):
        mine = Vehicle.objects.create(
            owner=self.consumer, registration_number="KA01AB1234"
        )
        Vehicle.objects.create(owner=self.other, registration_number="MH12XY9999")

        response = self.client.patch(
            f"/api/vehicles/{mine.pk}/",
            {
                "state_code": "MH",
                "rto_code": "12",
                "series": "XY",
                "unique_number": "9999",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("registration_number", response.data)

    def test_consumer_can_delete_their_own_vehicle(self):
        mine = Vehicle.objects.create(
            owner=self.consumer, registration_number="KA01AB1234"
        )

        response = self.client.delete(f"/api/vehicles/{mine.pk}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Vehicle.objects.filter(pk=mine.pk).exists())

    def test_staff_cannot_reach_the_vehicle_surface(self):
        for actor in (self.manager, self.admin):
            with self.subTest(actor=actor.role):
                self._authenticate(actor)
                response = self.client.get("/api/vehicles/")
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_gets_401(self):
        self.client.credentials()

        response = self.client.get("/api/vehicles/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
