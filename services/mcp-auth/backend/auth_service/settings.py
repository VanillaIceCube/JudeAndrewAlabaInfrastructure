"""Production settings: independent state and file-only secrets, fail closed."""
import os
from .base_settings import *  # noqa: F403
from .secrets import protected_text

SECRET_KEY = protected_text("/run/secrets/django_secret_key", maximum=512).strip()
if len(SECRET_KEY) < 50:
    raise ValueError("Authorization service secret prerequisite failed")
SIGNING_PRIVATE_KEY = protected_text("/run/secrets/signing_key.pem", maximum=16384)
SIGNING_KEY_ID = os.environ.get("MCP_AUTH_SIGNING_KEY_ID", "")
TRUSTED_PROXY_IPS = [value.strip() for value in os.environ.get("DJANGO_TRUSTED_PROXY_IPS", "").split(",") if value.strip()]
if not SIGNING_KEY_ID or len(SIGNING_KEY_ID) > 64 or not TRUSTED_PROXY_IPS:
    raise ValueError("Authorization service identity prerequisite failed")
