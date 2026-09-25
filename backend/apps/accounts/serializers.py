from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        validators=[
            UniqueValidator(queryset=User.objects.all(),
            lookup="iexact",
            message="An account with this email address already exists.")
        ]
    )

    password_confirm = serializers.CharField(
        write_only=True,
        style={"input_type" : "password"},
    )

    class Meta:
        model = User
        fields=[
            "id","email","full_name","phone","password","password_confirm",
        ]
        read_only_fields=["id"]

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm":"The two password fields did not match"}
            )

        candidate = User(email=attrs["email"], full_name=attrs["full_name"])
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password":exc.messages})

        return attrs

    def create(self, validated_data):
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
        # exists.
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data