import os
os.umask(0o077)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "auth_service.settings")
from django.conf import settings
from django.core.asgi import get_asgi_application
from mcp_framework.proxy import TrustedProxyHeadersMiddleware

application = TrustedProxyHeadersMiddleware(get_asgi_application(), settings.TRUSTED_PROXY_IPS)
