"""
Django settings for the SPMS backend.

Project layout (PROJECT.md §13, modular monolith):
    backend/
    ├── manage.py
    ├── config/          <- project configuration package (this module)
    └── apps/            <- domain apps (accounts, parking, bookings, ...)

Environment variables
---------------------
``backend/.env`` is loaded with the Python standard library only (no
third-party dotenv dependency). Loading is best-effort:

* If ``backend/.env`` exists, its ``KEY=VALUE`` pairs are placed into
  ``os.environ`` (real process environment variables always win, so
  production/CI values are never overwritten by the file).
* If the file is missing, ``os.environ`` is used as-is and the developer
  defaults below apply (documented LOCAL DEVELOPMENT FALLBACK).

For more information on settings, see:
https://docs.djangoproject.com/en/6.0/topics/settings/
"""

import os
from datetime import timedelta
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal, dependency-free ``.env`` loader.

    Parses simple ``KEY=VALUE`` lines, ignores blanks and ``#`` comments and
    strips a single layer of surrounding quotes. Existing environment
    variables are never overridden.
    """
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            # setdefault -> real environment wins over the .env file.
            os.environ.setdefault(key, value)


# Load backend/.env if present (see module docstring).
_load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable ('1', 'true', 'yes', 'on')."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

# SECURITY WARNING: keep the secret key used in production secret!
# LOCAL DEVELOPMENT FALLBACK: an insecure key is used when SECRET_KEY is unset
# so the project runs out of the box. Set SECRET_KEY in .env for real use.
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-dev-only-change-me-in-env",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env_bool("DEBUG", default=True)

# LOCAL DEVELOPMENT FALLBACK: allow the Vite dev server's host aliases.
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]


# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    # Third-party — "daphne" MUST stay first so runserver serves ASGI (D72).
    "daphne",
    # Django contrib
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "channels",
    "rest_framework_simplejwt.token_blacklist",
    "rest_framework",
    "corsheaders",
    # Local domain apps (modular monolith, PROJECT.md §13/§14)
    "apps.accounts",
    "apps.parking",
    "apps.bookings",
    "apps.payments",
    "apps.notifications",
    "apps.reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # CorsMiddleware must sit as high as possible and above CommonMiddleware.
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ---------------------------------------------------------------------------
# Database (PostgreSQL — mandatory, PROJECT.md §12)
# ---------------------------------------------------------------------------

# LOCAL DEVELOPMENT FALLBACK: if DB_* variables are absent, local PostgreSQL
# defaults are used. Migrating away from PostgreSQL is forbidden, so the
# engine default is fixed to the PostgreSQL backend.
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": os.environ.get("DB_NAME", "spms"),
        "USER": os.environ.get("DB_USER", "maytrix"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
        "OPTIONS": {
            "connect_timeout": int(os.environ.get("DB_CONNECT_TIMEOUT", "10")),
        },
    }
}


# ---------------------------------------------------------------------------
# Authentication / authorization
# ---------------------------------------------------------------------------

# Custom email-based user model (apps.accounts.User). Django requires this to be
# set before the first accounts migration is applied, which is why the database
# was reset before generating that migration.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    # B4: the default attribute list is ('username', 'first_name',
        # 'last_name', 'email'), none of which is this model's name field, so
        # full_name was never compared. Point the validator at the fields this
        # model actually has. The registration serializer already builds its
        # unsaved User with both, so no serializer change is needed.
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS" : {"user_attributes": ("email", "full_name")},
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# JWT (djangorestframework-simplejwt) is the agreed auth mechanism (D1). It is
# configured in the SIMPLE_JWT block below and selected through
# DEFAULT_AUTHENTICATION_CLASSES above.


# ---------------------------------------------------------------------------
# Internationalization / time
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"

# Timestamps are stored in UTC (USE_TZ=True) per the agreed time policy.
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Report day-bucketing timezone (reports app only). Distinct from TIME_ZONE:
# the database remains UTC, but business days are grouped in IST.
BUSINESS_TIMEZONE = os.environ.get("BUSINESS_TIMEZONE", "Asia/Kolkata")


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATIC_URL = "static/"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "config.pagination.DefaultPagination",
}

# ---------------------------------------------------------------------------
# JWT (djangorestframework-simplejwt) — D1
# ---------------------------------------------------------------------------

# Access tokens CANNOT be revoked once issued; only refresh tokens can be
# blacklisted. The access lifetime is therefore the only bound on how long a
# leaked access token stays useful, so keep it short.
JWT_ACCESS_TOKEN_MINUTES = int(os.environ.get("JWT_ACCESS_TOKEN_MINUTES", "30"))
JWT_REFRESH_TOKEN_DAYS = int(os.environ.get("JWT_REFRESH_TOKEN_DAYS", "7"))

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=JWT_ACCESS_TOKEN_MINUTES),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=JWT_REFRESH_TOKEN_DAYS),
    # Refresh tokens are single-use: /api/auth/refresh/ returns a new refresh
    # token and blacklists the one presented. A stolen refresh token is usable
    # at most once, and the thief's use invalidates the legitimate session --
    # a detectable signal rather than silent long-term access.
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    # Keep the Django admin's "last login" column accurate.
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    # Separate signing key so rotating SECRET_KEY does not silently invalidate
    # every issued token, and vice versa. Falls back to SECRET_KEY when unset.
    "SIGNING_KEY": os.environ.get("JWT_SIGNING_KEY") or SECRET_KEY,
}


# ---------------------------------------------------------------------------
# CORS (local development only — PROJECT.md §30/§45)
# ---------------------------------------------------------------------------

# Allow the Vite dev server origin to call the API during development.
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]

CHANNEL_LAYERS = {
    "default" : {
        "BACKEND" : "channels_redis.core.RedisChannelLayer",
        "CONFIG" : {
            "hosts" : [os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")],
        },
    },
}

# No cross-site cookies are needed: JWT will be sent in the Authorization
# header (not cookies), so credentials are intentionally left disabled to
# avoid over-permitting. Enable via env only if a cookie scheme is adopted.
CORS_ALLOW_CREDENTIALS = env_bool("CORS_ALLOW_CREDENTIALS", default=False)

CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# ---------------------------------------------------------------------------
# Payment gateway (Phase 5 — D56 revised / D58)
# ---------------------------------------------------------------------------

# Which PaymentGateway adapter to use: "mock" (offline, deterministic; the
# default so development and the test suite need no network or credentials) or
# "razorpay" (test-mode sandbox). Only the adapter imports the provider SDK.
PAYMENT_GATEWAY = os.environ.get("PAYMENT_GATEWAY", "mock").strip().lower()

# Razorpay **test-mode** credentials. TEST keys only (rzp_test_...); NEVER live
# keys and NEVER committed (D9/D56 revised). Blank by default, because the mock
# path needs no secrets.
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")