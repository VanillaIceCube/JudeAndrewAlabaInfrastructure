"""Service policy around maintained DOT/OAuthlib protocol and PyJWT signing."""
import time
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from oauth2_provider.models import Application, Grant
from .models import ClientPolicy
from oauth2_provider.oauth2_validators import OAuth2Validator
from oauthlib.oauth2.rfc6749.errors import CustomOAuth2Error


def policy_for(client):
    try:
        policy = client.mcp_policy
    except (AttributeError, ObjectDoesNotExist):
        return None
    if (policy.resource not in settings.RESOURCE_SCOPES
            or policy.resource == settings.YNAB_RESOURCE and not policy.allowed_user_id
            or client.client_type != Application.CLIENT_PUBLIC
            or client.skip_authorization
            or client.authorization_grant_type != Application.GRANT_AUTHORIZATION_CODE):
        return None
    if (policy.resource == settings.YNAB_RESOURCE and ClientPolicy.objects.filter(
            resource=settings.YNAB_RESOURCE).exclude(allowed_user_id=policy.allowed_user_id).exists()):
        return None
    return policy


def owner_allowed(policy, user):
    return (policy is not None and user is not None and user.is_active
            and (policy.allowed_user_id is None or user.pk == policy.allowed_user_id))


def invalid_target(request):
    raise CustomOAuth2Error(error="invalid_target", description="The registered resource and owner are required.", request=request)


class AuthorizationValidator(OAuth2Validator):
    def authenticate_client(self, request, *args, **kwargs):
        if not super().authenticate_client(request, *args, **kwargs):
            return False
        if request.uri.split("?", 1)[0].endswith("/o/introspect/"):
            return (request.client.client_id in settings.INTROSPECTION_RESOURCES
                    and request.client.client_type == Application.CLIENT_CONFIDENTIAL)
        return True

    def validate_grant_type(self, client_id, grant_type, client, request, *args, **kwargs):
        return (policy_for(client) is not None and grant_type in {"authorization_code", "refresh_token"}
                and super().validate_grant_type(client_id, grant_type, client, request, *args, **kwargs))

    def validate_scopes(self, client_id, scopes, client, request, *args, **kwargs):
        policy = policy_for(client)
        return (policy is not None and set(scopes) <= set(settings.RESOURCE_SCOPES[policy.resource])
                and next(iter(settings.RESOURCE_SCOPES[policy.resource])) in scopes
                and super().validate_scopes(client_id, scopes, client, request, *args, **kwargs))

    def validate_redirect_uri(self, client_id, redirect_uri, request, *args, **kwargs):
        from .registration import valid_callback
        return valid_callback(redirect_uri) and super().validate_redirect_uri(client_id, redirect_uri, request, *args, **kwargs)

    def confirm_redirect_uri(self, client_id, code, redirect_uri, client, *args, **kwargs):
        grant = Grant.objects.filter(code=code, application=client).first()
        return grant is not None and redirect_uri == grant.redirect_uri

    def get_default_scopes(self, client_id, request, *args, **kwargs):
        policy = policy_for(request.client)
        return [next(iter(settings.RESOURCE_SCOPES[policy.resource]))] if policy else []

    def _validate_resource_uris(self, request, resources):
        super()._validate_resource_uris(request, resources)
        policy = policy_for(request.client)
        if policy is None or any(resource != policy.resource for resource in resources):
            invalid_target(request)

    def _check_and_set_request_resource(self, request):
        super()._check_and_set_request_resource(request)
        policy = policy_for(request.client)
        if policy is None or request.resource != [policy.resource] or not owner_allowed(policy, request.user):
            invalid_target(request)

    def validate_code(self, client_id, code, client, request, *args, **kwargs):
        return (super().validate_code(client_id, code, client, request, *args, **kwargs)
                and owner_allowed(policy_for(client), request.user))

    def validate_refresh_token(self, refresh_token, client, request, *args, **kwargs):
        return (super().validate_refresh_token(refresh_token, client, request, *args, **kwargs)
                and owner_allowed(policy_for(client), request.user))


def signing_key():
    try:
        key = serialization.load_pem_private_key(settings.SIGNING_PRIVATE_KEY.encode(), password=None)
        if not isinstance(key, RSAPrivateKey) or key.key_size < 2048:
            raise ValueError()
        return key
    except (ValueError, TypeError):
        raise ValueError("Authorization signing prerequisite failed") from None


def access_token(request):
    # OAuthlib calls the generator before DOT persists and normalizes resources.
    # Reuse DOT's normalization/inheritance validation before signing anything.
    validator = AuthorizationValidator()
    validator._check_and_set_request_resource(request)
    policy = policy_for(request.client)
    scopes = list(request.scopes or [])
    if not validator.validate_scopes(request.client.client_id, scopes, request.client, request):
        invalid_target(request)
    now = int(time.time())
    claims = {"iss": settings.ISSUER, "sub": str(request.user.pk), "aud": policy.resource,
              "client_id": request.client.client_id, "scope": " ".join(scopes),
              "iat": now, "exp": now + 900, "jti": str(uuid.uuid4())}
    return jwt.encode(claims, signing_key(), algorithm="RS256",
                      headers={"typ": "at+jwt", "kid": settings.SIGNING_KEY_ID})
