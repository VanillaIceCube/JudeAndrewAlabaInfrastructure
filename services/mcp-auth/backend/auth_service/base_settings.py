"""Non-secret service policy. Runtime settings load protected files separately."""
from pathlib import Path
import os

from mcp_framework.config import oauth_settings

BASE_DIR = Path(__file__).resolve().parent.parent
ISSUER = "https://auth.judeandrewalaba.com"
YNAB_RESOURCE = "https://ynab.judeandrewalaba.com/mcp"
NOTOLI_RESOURCE = "https://notoli.judeandrewalaba.com/mcp"
MACROMAPPER_RESOURCE = "https://macromapper.judeandrewalaba.com/mcp"
RESOURCE_SCOPES = {
    YNAB_RESOURCE: {
        "ynab:read": "Read your YNAB budget and operation history",
        "ynab:write": "Change your YNAB budget after an exact preview and your explicit confirmation",
    },
    NOTOLI_RESOURCE: {
        "notoli:read": "Read boards, lists and items you can access",
        "notoli:write": "Add and update accessible items",
        "notoli:organize": "Create and organize accessible boards, lists and items",
        "notoli:notifications": "Read and update your notifications",
        "notoli:delete": "Delete accessible content and your notifications",
        "notoli:share": "Manage collaborators on boards you own",
    },
    MACROMAPPER_RESOURCE: {
        "macromapper:read": "Read MacroMapper data you can access",
        "macromapper:write": "Add and update your MacroMapper data",
    },
}
INTROSPECTION_RESOURCES = {
    "notoli-introspection": NOTOLI_RESOURCE,
    "macromapper-introspection": MACROMAPPER_RESOURCE,
}
DEBUG = False
ALLOWED_HOSTS = ["auth.judeandrewalaba.com", "172.30.92.3"]
DATA_UPLOAD_MAX_MEMORY_SIZE = 16384
DATA_UPLOAD_MAX_NUMBER_FIELDS = 32
AUTH_USER_MODEL = "auth_service.User"
OAUTH2_PROVIDER_APPLICATION_MODEL = "oauth2_provider.Application"
ROOT_URLCONF = "auth_service.urls"
ASGI_APPLICATION = "auth_service.asgi.application"
INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "django.contrib.staticfiles", "oauth2_provider", "auth_service",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "auth_service.middleware.PrivateResponses",
]
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True,
              "OPTIONS": {"context_processors": ["django.template.context_processors.request",
                                                  "django.contrib.auth.context_processors.auth"]}}]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3",
                         "NAME": os.environ.get("MCP_AUTH_DATABASE_PATH", "/data/db.sqlite3"),
                         "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"}}}
USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/o/authorized_tokens/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 3600
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_TRUSTED_ORIGINS = [ISSUER]
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/(live|ready)$"]
SECURE_HSTS_SECONDS = 31536000
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
USE_X_FORWARDED_HOST = False
STATIC_URL = "/static/"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 14}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
OAUTH2_PROVIDER = oauth_settings(
    ISSUER, {scope: label for scopes in RESOURCE_SCOPES.values() for scope, label in scopes.items()},
    [], validator="auth_service.oauth.AuthorizationValidator")
OAUTH2_PROVIDER.update({
    "ACCESS_TOKEN_EXPIRE_SECONDS": 900,
    "ACCESS_TOKEN_GENERATOR": "auth_service.oauth.access_token",
    "REFRESH_TOKEN_GENERATOR": "oauthlib.oauth2.rfc6749.tokens.random_token_generator",
    "ALLOWED_REDIRECT_URI_SCHEMES": ["https", "http"],
    "OAUTH2_TOKEN_ENDPOINT_AUTH_METHODS_SUPPORTED": ["none"],
    "COMPLIANT_BCP_RFC9700_REDIRECT_URI_MATCHING": True,
    "DCR_ENABLED": False, "CIMD_ENABLED": False,
})
LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"null": {"class": "logging.NullHandler"}},
           "loggers": {name: {"handlers": ["null"], "propagate": False}
                       for name in ("django.request", "django.security", "oauthlib", "oauth2_provider")}}
