"""Tests for the accounts domain.

Automated testing is incremental rather than deferred to Phase 10 (PROJECT.md
§34 puts authorization rules explicitly in unit-test scope). The role permission
classes have no consumer endpoint yet, so a unit test is the only way to verify
them at all.

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

from .models import User
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
