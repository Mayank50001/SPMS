from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db.models import Q
from .models import User
from .permissions import IsAdmin

from .serializers import (
    LoginSerializer,
    PrivilegedUserCreateSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    UserAccessUpdateSerializer,
    UserSerializer,
)
from .services import LastAdministratorError, update_user_access


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        raw_refresh = request.data.get("refresh")
        if not raw_refresh:
            return Response(
                {"refresh": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            RefreshToken(raw_refresh).blacklist()
        except TokenError:
            return Response(
                {"refresh":["This token is invalid or has already been revoked."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)

class MeView(generics.RetrieveUpdateAPIView):
    """Read or update the caller's own profile.

    GET   /api/auth/me/  -> UserSerializer (full read shape)
    PATCH /api/auth/me/  -> ProfileUpdateSerializer (full_name, phone)

    The object is always ``request.user`` and no id appears in the URL, so a
    consumer can only ever read or modify their own account (Invariant 2). PUT is
    excluded so a client that omits fields cannot blank the profile.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get","patch","head","options"]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ProfileUpdateSerializer
        return UserSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(UserSerializer(instance).data)

class UserListCreateView(generics.ListCreateAPIView):
    """Administrator-only user directory and privileged account creation (D20).

    GET  /api/users/  -> list accounts, optionally filtered
    POST /api/users/  -> create a MANAGER or ADMIN account

    Only an Administrator reaches either method; ``IsAdmin`` performs its own
    authentication check (permissions.py), because setting ``permission_classes``
    replaces the project-wide ``IsAuthenticated`` default (D18).
    """

    permission_classes = [IsAdmin]
    queryset = User.objects.all().order_by("id")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PrivilegedUserCreateSerializer
        return UserSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        role = self.request.query_params.get("role")
        if role:
            queryset = queryset.filter(role=role)

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(
                is_active = is_active.lower() in {"1", "true", "yes"}
            )

        search = self.request.query_params.get("search")
        if search:
            queryset=queryset.filter(
                Q(email__icontains=search) | Q(full_name__icontains=search)
            )

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

class UserDetailView(generics.RetrieveUpdateAPIView):
    """Administrator-only retrieval and access management of one account (D24).

    ``GET``  -> ``UserSerializer`` (read shape)
    ``PATCH`` -> role change and/or suspend-activate; both fields are optional
                but at least one is required, and ``PUT`` is disabled so a
                partial payload cannot blank the account.

    The write is delegated to ``services.update_user_access`` so the
    last-Administrator guard and its row locking are applied on every path.
    A refusal (``LastAdministratorError``) becomes ``409`` with a stable
    ``error`` code (PROJECT.md §33) instead of a bare validation error.
    """

    permission_classes = [IsAdmin]
    queryset = User.objects.all()
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return UserAccessUpdateSerializer
        return UserSerializer

    def update(self, request, *args, **kwargs):
        target = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            updated = update_user_access(
                target_id=target.pk,
                role=serializer.validated_data.get("role"),
                is_active=serializer.validated_data.get("is_active"),
            )
        except LastAdministratorError as exc:
            return Response(
                {"error": "LAST_ADMINISTRATOR", "message": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(UserSerializer(updated).data)
