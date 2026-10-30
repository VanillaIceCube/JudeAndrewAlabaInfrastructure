"""Small policy adapters; protocol, login, consent and revocation remain DOT/Django."""
import hashlib
import json
import time

import jwt
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET
from oauth2_provider.models import AccessToken, Application
from oauth2_provider.views import AuthorizationView
from oauth2_provider.views import OAuthServerMetadataView
from oauth2_provider.views.mixins import OAuthLibMixin
from oauthlib.common import Request as OAuthRequest

from .oauth import owner_allowed, policy_for, signing_key


class MetadataView(OAuthServerMetadataView):
    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        metadata = json.loads(response.content)
        metadata["introspection_endpoint_auth_methods_supported"] = ["client_secret_basic"]
        result = JsonResponse(metadata)
        result["Access-Control-Allow-Origin"] = "*"
        return result


@method_decorator(never_cache, name="dispatch")
@method_decorator(sensitive_post_parameters(), name="dispatch")
class ConsentView(AuthorizationView):
    def dispatch(self, request, *args, **kwargs):
        if request.method not in {"GET", "POST"}:
            return JsonResponse({"error": "invalid_request"}, status=405)
        data = request.GET if request.method == "GET" else request.POST
        client = Application.objects.filter(client_id=data.get("client_id")).first()
        policy = policy_for(client)
        if (policy is None or data.getlist("resource") != [policy.resource]
                or data.get("code_challenge_method") != "S256" or not data.get("state")
                or data.get("approval_prompt", "force") != "force"):
            return JsonResponse({"error": "invalid_request"}, status=400)
        if request.user.is_authenticated and not owner_allowed(policy, request.user):
            return JsonResponse({"error": "access_denied"}, status=403)
        return super().dispatch(request, *args, **kwargs)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(never_cache, name="dispatch")
@method_decorator(sensitive_post_parameters(), name="dispatch")
class IntrospectionView(OAuthLibMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        # Deliberately do not use ClientProtectedResourceMixin's bearer fallback.
        header = request.headers.get("Authorization", "")
        if (request.GET or request.content_type != "application/x-www-form-urlencoded"
                or set(request.POST) - {"token", "token_type_hint"}
                or any(len(request.POST.getlist(key)) != 1 for key in request.POST)):
            return JsonResponse({"error": "invalid_request"}, status=400)
        # Use DOT's pinned extraction/authentication without its bearer fallback,
        # retaining the authenticated client solely for audience authorization.
        core = self.get_oauthlib_core()
        oauth_request = OAuthRequest(*core._extract_params(request))
        if (not header.lower().startswith("basic ") or len(header) > 2048
                or not core.server.request_validator.authenticate_client(oauth_request)):
            return JsonResponse({"error": "invalid_client"}, status=401,
                                headers={"WWW-Authenticate": 'Basic realm="mcp-introspection"'})
        resource = settings.INTROSPECTION_RESOURCES[oauth_request.client.client_id]
        required_read = next(iter(settings.RESOURCE_SCOPES[resource]))
        raw = request.POST.get("token", "")
        if not raw or len(raw) > 8192:
            return JsonResponse({"active": False})
        token = AccessToken.objects.select_related("user", "application").filter(
            token_checksum=hashlib.sha256(raw.encode()).hexdigest()).first()
        policy = policy_for(token.application) if token and token.application else None
        if (not token or not token.is_valid([required_read]) or not owner_allowed(policy, token.user)
                or policy.resource != resource or token.resource != [resource]):
            return JsonResponse({"active": False})
        try:
            claims = jwt.decode(raw, signing_key().public_key(), algorithms=["RS256"],
                                audience=resource, issuer=settings.ISSUER,
                                options={"require": ["iss", "sub", "aud", "client_id", "scope", "iat", "exp", "jti"]})
            now = time.time()
            if (jwt.get_unverified_header(raw).get("typ") != "at+jwt"
                    or type(claims["iat"]) is not int or type(claims["exp"]) is not int
                    or not claims["iat"] <= now + 5 or not now < claims["exp"] <= claims["iat"] + 900
                    or claims["exp"] > int(token.expires.timestamp())
                    or claims["sub"] != str(token.user.pk) or claims["client_id"] != token.application.client_id
                    or claims["aud"] != resource or claims["scope"] != token.scope):
                raise ValueError()
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            return JsonResponse({"active": False})
        return JsonResponse({"active": True, **{key: claims[key] for key in
                            ("iss", "sub", "aud", "client_id", "scope", "iat", "exp")}})


@require_GET
def live(request):
    return JsonResponse({"status": "live"})


@require_GET
def ready(request):
    try:
        signing_key()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM auth_service_user LIMIT 1")
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready"})
