"""Synthetic local test settings, never copied into the production image."""
import os
from pathlib import Path
from auth_service.base_settings import *  # noqa: F403

SECRET_KEY = "synthetic-test-key-that-is-not-a-runtime-credential" * 2
SIGNING_PRIVATE_KEY = Path(os.environ["MCP_AUTH_TEST_KEY_PATH"]).read_text()
SIGNING_KEY_ID = "synthetic-key-1"
TRUSTED_PROXY_IPS = ["127.0.0.2"]
ALLOWED_HOSTS = ["testserver", "auth.judeandrewalaba.com"]
DATABASES["default"]["NAME"] = os.environ["MCP_AUTH_TEST_DB_PATH"]
DATABASES["default"]["TEST"] = {"NAME": os.environ["MCP_AUTH_TEST_DB_PATH"] + ".test"}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
