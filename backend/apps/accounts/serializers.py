"""Account serializers.

Import-time constraint (B5)
---------------------------
``User = get_user_model()`` below resolves the concrete model class as this
module is imported, because DRF's ``ModelSerializer`` requires a real class in
``Meta.model`` -- it does **not** accept a lazy ``"app.Model"`` string. Resolving
the model this early means the module may only be imported once Django's app
registry is ready (i.e. after normal startup).

That holds today: this module is imported by ``apps/accounts/views.py``, which
the URLconf and the admin load after startup. Do **not** import it from
``models.py``, ``apps.py`` or any other app-loading code, or startup will fail
with ``AppRegistryNotReady``. If a future feature genuinely needs a serializer
during app loading, convert it to a plain ``serializers.Serializer`` and call
``get_user_model()`` inside its methods.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

class PhoneValidationMixin:
    """Shared phone normalisation and validation for write serializers (D23).

    The canonical rule lives on the model (``User.normalize_phone``) so every
    write path is covered; this mixin adds the user-facing check and error at the
    API boundary. It is a mixin rather than two copies so the rule has a single
    definition. ``max_length`` is generous because the *raw* input may contain
    separators; the stored value is [digits only, validated to 7-15].
    """

    phone = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=20,
    )

    def validate_phone(self, value):
        normalized = User.normalize_phone(value)
        if normalized is None:
            return None
        if not normalized.isdigit() or not (7 <= len(normalized) <= 15):
            raise serializers.ValidationError("Enter a valid phone number (7 to 15 digits).")
        return normalized

class RegisterSerializer(PhoneValidationMixin, serializers.ModelSerializer):
    """Create a self-registered Consumer (PROJECT.md §16, D11, D20).

    ``role`` is deliberately absent from ``Meta.fields``, so a client cannot
    propose one; the model default (``CONSUMER``) applies. Both password fields
    are ``write_only``, so neither the raw password nor its hash can be
    serialised back out (B2).
    """

    email = serializers.EmailField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                lookup="iexact",
                message="An account with this email address already exists.",
            )
        ]
    )

    # Declared explicitly and ``write_only`` so the stored hash is never
    # returned (B2). ``max_length`` mirrors AbstractBaseUser.password's model
    # field; omitting it would silently drop the limit that the auto-generated
    # field used to carry.
    password = serializers.CharField(
        write_only=True,
        max_length=128,
        style={"input_type": "password"},
    )

    password_confirm = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "phone",
            "password",
            "password_confirm",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "The two password fields did not match"}
            )

        # An unsaved User is passed so UserAttributeSimilarityValidator can
        # compare the password against the incoming email and full name (D22).
        candidate = User(email=attrs["email"], full_name=attrs["full_name"])
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages})

        return attrs

    def create(self, validated_data):
        # Delegates to the manager so the password is hashed and the email is
        # canonicalised (D12, D13). The default ModelSerializer.create() would
        # store the password in clear text.
        validated_data.pop("password_confirm")
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    """Read-only representation of an account.

    Deliberately read-only: this shape is returned by login and by
    ``GET /api/auth/me/``, and nothing writes accounts through it. ``password``
    is not a field here, so it cannot be leaked by accident.
    """

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "role", "created_at"]
        read_only_fields = fields

class ProfileUpdateSerializer(PhoneValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["full_name", "phone"]

    def validate_full_name(self, value):
        # PATCH is partial, so an omitted field is fine; but an explicitly blank
        # name is not (the model field is non-blank). CharField already rejects
        # "" by default; this guards whitespace-only input such as "   ".
        if not value.strip():
            raise serializers.ValidationError("Full name cannot be blank.")
        return value.strip()

class PrivilegedUserCreateSerializer(PhoneValidationMixin, serializers.ModelSerializer):
    PRIVILEGED_ROLES = [
        (User.Role.MANAGER.value, User.Role.MANAGER.label),
        (User.Role.ADMIN.value, User.Role.ADMIN.label),
    ]

    email = serializers.EmailField(
        validators = [
            UniqueValidator(
                queryset=User.objects.all(),
                lookup="iexact",
                message="An account with this email address already exists.",
            )
        ]
    )

    role = serializers.ChoiceField(choices=PRIVILEGED_ROLES)

    password = serializers.CharField(
        write_only = True,
        max_length = 128,
        style={"input_type", "password"},
    )

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "role", "password"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        # Same password policy as self-registration (D14), invoked at object
        # level so UserAttributeSimilarityValidator receives the candidate.
        candidate = User(email = attrs["email"], full_name=attrs["full_name"])
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages})
        return attrs

    def create(self, validated_data):
        # The manager hashes the password and canonicalises the email/phone
        # (D12, D13, D23). is_staff / is_superuser are intentionally not set:
        # API authority (role) and Django-admin access (is_staff) are separate.
        return User.objects.create_user(**validated_data) 


class LoginSerializer(TokenObtainPairSerializer):
    """Email/password login returning a token pair plus the account profile.

    Extends simplejwt's serializer rather than reimplementing it, so claim
    construction, lifetimes, rotation and blacklisting all stay in simplejwt's
    hands. The single addition is the ``user`` object.

    ``role`` is added to the RESPONSE BODY only, never to the token claims
    (D15). Every request re-reads the account from the database, so
    ``request.user.role`` is always current; a role embedded in a token would be
    a second, staler source of truth and nothing in the backend needs it.
    """

    def validate(self, attrs):
        # Raises AuthenticationFailed (401) for bad credentials AND for
        # is_active=False, so a suspended account never receives a token. The
        # message is intentionally vague so it does not reveal whether the email
        # exists. Email case-insensitivity is handled inside
        # UserManager.get_by_natural_key, not here.
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data