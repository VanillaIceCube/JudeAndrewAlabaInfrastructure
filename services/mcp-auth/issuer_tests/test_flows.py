import base64
import hashlib
import os
import subprocess
import sys
from io import StringIO
from html.parser import HTMLParser
from datetime import timedelta
from pathlib import Path
import tempfile
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application, Grant, RefreshToken
from auth_service.models import ClientPolicy, User
from auth_service.oauth import signing_key
from auth_service.registration import valid_callback


class Flows(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="synthetic-owner", password="synthetic-password")
        cls.other = User.objects.create_user(username="synthetic-other", password="synthetic-password")
        cls.apps = {}
        for resource, name in ((settings.YNAB_RESOURCE, "ynab"), (settings.NOTOLI_RESOURCE, "notoli"),
                               (settings.MACROMAPPER_RESOURCE, "macromapper")):
            for host in ("chatgpt", "codex"):
                client_id = name + "-" + host
                app = Application.objects.create(client_id=client_id, name=client_id,
                    user=cls.owner, client_type="public", authorization_grant_type="authorization-code",
                    redirect_uris="https://client.example/callback" if host == "chatgpt" else "http://127.0.0.1/callback")
                ClientPolicy.objects.create(application=app, resource=resource,
                                           allowed_user=cls.owner if name == "ynab" else None)
                cls.apps[client_id] = app
        cls.secret = "synthetic-introspector-secret-" * 3
        cls.inspector = Application.objects.create(client_id="notoli-introspection", user=cls.owner,
            client_type="confidential", authorization_grant_type="client-credentials", client_secret=cls.secret)
        cls.macro_secret = "synthetic-macro-introspector-secret-" * 3
        Application.objects.create(client_id="macromapper-introspection", user=cls.owner,
            client_type="confidential", authorization_grant_type="client-credentials", client_secret=cls.macro_secret)

    def setUp(self):
        self.browser = Client()
        self.browser.force_login(self.owner)
        self.verifier = "synthetic-verifier-" * 4
        self.challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).rstrip(b"=").decode()

    def authorization(self, client_id="notoli-chatgpt", **overrides):
        app = self.apps[client_id]
        data = dict(client_id=client_id, redirect_uri=app.redirect_uris, scope=app.mcp_policy.resource.split(":")[0],
                    response_type="code", state="synthetic-state", code_challenge=self.challenge,
                    code_challenge_method="S256", resource=app.mcp_policy.resource)
        namespace = client_id.split("-")[0]
        data["scope"] = namespace + ":read" + (" " + namespace + ":write" if namespace != "ynab" else "")
        data.update(overrides)
        return data

    def code(self, client_id="notoli-chatgpt", **overrides):
        data = self.authorization(client_id, **overrides)
        before = Grant.objects.count()
        response = self.browser.get("/o/authorize/", data, secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Authorize")
        self.assertEqual(Grant.objects.count(), before)
        data["allow"] = "Authorize"
        response = self.browser.post("/o/authorize/", data, secure=True)
        self.assertEqual(response.status_code, 302)
        params = parse_qs(urlsplit(response["Location"]).query)
        self.assertEqual(params["iss"], [settings.ISSUER])
        return params["code"][0], data["redirect_uri"]

    def post_token(self, **data):
        return self.client.post("/o/token/", urlencode(data), content_type="application/x-www-form-urlencoded", secure=True)

    def issue(self, client_id="notoli-chatgpt"):
        code, callback = self.code(client_id)
        response = self.post_token(grant_type="authorization_code", client_id=client_id,
                                   code=code, redirect_uri=callback, code_verifier=self.verifier)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def introspect(self, token, **extra):
        header = "Basic " + base64.b64encode(("notoli-introspection:" + self.secret).encode()).decode()
        return self.client.post("/o/introspect/", urlencode({"token": token, **extra}),
                                content_type="application/x-www-form-urlencoded", secure=True, HTTP_AUTHORIZATION=header)

    def test_real_code_jwt_rotation_replay_and_revocation(self):
        tokens = self.issue()
        claims = jwt.decode(tokens["access_token"], signing_key().public_key(), algorithms=["RS256"],
                            audience=settings.NOTOLI_RESOURCE, issuer=settings.ISSUER)
        self.assertEqual(claims["sub"], str(self.owner.pk))
        self.assertEqual(claims["client_id"], "notoli-chatgpt")
        self.assertEqual(claims["exp"] - claims["iat"], 900)
        self.assertEqual(jwt.get_unverified_header(tokens["access_token"])["typ"], "at+jwt")
        self.assertNotIn(".", tokens["refresh_token"])
        self.assertNotEqual(AccessToken.objects.get().token, tokens["access_token"])
        self.assertTrue(self.introspect(tokens["access_token"]).json()["active"])
        rotated = self.post_token(grant_type="refresh_token", client_id="notoli-chatgpt", refresh_token=tokens["refresh_token"])
        self.assertEqual(rotated.status_code, 200, rotated.content)
        self.assertNotEqual(rotated.json()["refresh_token"], tokens["refresh_token"])
        replay = self.post_token(grant_type="refresh_token", client_id="notoli-chatgpt", refresh_token=tokens["refresh_token"])
        self.assertEqual(replay.status_code, 400)
        self.assertFalse(self.introspect(rotated.json()["access_token"]).json()["active"])
        tokens = self.issue()
        revoked = self.client.post("/o/revoke_token/", urlencode(dict(token=tokens["refresh_token"], client_id="notoli-chatgpt")),
                                   content_type="application/x-www-form-urlencoded", secure=True)
        self.assertEqual(revoked.status_code, 200)
        self.assertFalse(self.introspect(tokens["access_token"]).json()["active"])

    def test_s256_callback_code_replay_and_client_isolation(self):
        code, callback = self.code()
        wrong = self.post_token(grant_type="authorization_code", client_id="notoli-codex", code=code,
                                redirect_uri=callback, code_verifier=self.verifier)
        self.assertEqual(wrong.status_code, 400)
        wrong = self.post_token(grant_type="authorization_code", client_id="notoli-chatgpt", code=code,
                                redirect_uri=callback + "?extra=1", code_verifier=self.verifier)
        self.assertEqual(wrong.status_code, 400)
        wrong = self.post_token(grant_type="authorization_code", client_id="notoli-chatgpt", code=code,
                                redirect_uri=callback, code_verifier="wrong" * 12)
        self.assertEqual(wrong.status_code, 400)
        data = dict(grant_type="authorization_code", client_id="notoli-chatgpt", code=code,
                    redirect_uri=callback, code_verifier=self.verifier)
        self.assertEqual(self.post_token(**data).status_code, 200)
        self.assertEqual(self.post_token(**data).status_code, 400)

    def test_resource_scope_owner_and_disabled_user(self):
        for overrides in ({"resource": settings.YNAB_RESOURCE}, {"code_challenge_method": "plain"}, {"state": ""}):
            self.assertEqual(self.browser.get("/o/authorize/", self.authorization(**overrides), secure=True).status_code, 400)
        denied = self.browser.get("/o/authorize/", self.authorization(scope="notoli:read ynab:read"), secure=True)
        self.assertNotEqual(denied.status_code, 200)
        self.browser.force_login(self.other)
        self.assertEqual(self.browser.get("/o/authorize/", self.authorization("ynab-chatgpt"), secure=True).status_code, 403)
        self.browser.force_login(self.owner)
        ynab = self.issue("ynab-chatgpt")
        self.assertFalse(self.introspect(ynab["access_token"]).json()["active"])
        tokens = self.issue()
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.assertFalse(self.introspect(tokens["access_token"]).json()["active"])
        self.assertEqual(self.post_token(grant_type="refresh_token", client_id="notoli-chatgpt",
                                        refresh_token=tokens["refresh_token"]).status_code, 400)

    def test_introspection_auth_and_no_public_or_machine_tokens(self):
        tokens = self.issue()
        for header in ("", "Bearer " + tokens["access_token"], "Basic " + base64.b64encode(b"notoli-chatgpt:").decode()):
            response = self.client.post("/o/introspect/", urlencode({"token": tokens["access_token"]}),
                content_type="application/x-www-form-urlencoded", secure=True, HTTP_AUTHORIZATION=header)
            self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.get("/o/introspect/", secure=True).status_code, 405)
        self.assertEqual(self.introspect(tokens["access_token"], client_secret=self.secret).status_code, 400)
        header = "Basic " + base64.b64encode(("notoli-introspection:" + self.secret).encode()).decode()
        response = self.client.post("/o/token/", "grant_type=client_credentials", secure=True,
                                    content_type="application/x-www-form-urlencoded", HTTP_AUTHORIZATION=header)
        self.assertEqual(response.status_code, 400)

    def test_ynab_writes_require_explicit_consent_and_cannot_escalate_refresh(self):
        readonly = self.issue("ynab-chatgpt")
        claims = jwt.decode(readonly["access_token"], signing_key().public_key(), algorithms=["RS256"],
                            audience=settings.YNAB_RESOURCE, issuer=settings.ISSUER)
        self.assertEqual(claims["scope"], "ynab:read")
        escalated = self.post_token(grant_type="refresh_token", client_id="ynab-chatgpt",
            refresh_token=readonly["refresh_token"], scope="ynab:read ynab:write")
        self.assertEqual(escalated.status_code, 400)
        for client in ("ynab-chatgpt", "ynab-codex"):
            requested = self.authorization(client, scope="ynab:read ynab:write")
            consent = self.browser.get("/o/authorize/", requested, secure=True)
            self.assertContains(consent, "explicit confirmation")
            code, callback = self.code(client, scope="ynab:read ynab:write")
            issued = self.post_token(grant_type="authorization_code", client_id=client,
                code=code, redirect_uri=callback, code_verifier=self.verifier)
            self.assertEqual(issued.status_code, 200, issued.content)
            claims = jwt.decode(issued.json()["access_token"], signing_key().public_key(), algorithms=["RS256"],
                                audience=settings.YNAB_RESOURCE, issuer=settings.ISSUER)
            self.assertEqual(set(claims["scope"].split()), {"ynab:read", "ynab:write"})
            self.assertEqual(claims["client_id"], client)
            self.assertEqual(claims["sub"], str(self.owner.pk))
        for client, scope in (("ynab-chatgpt", "ynab:write"), ("notoli-chatgpt", "notoli:read ynab:write")):
            rejected = self.browser.get("/o/authorize/", self.authorization(client, scope=scope), secure=True)
            self.assertNotEqual(rejected.status_code, 200)

    def test_three_resource_introspection_and_refresh_isolation(self):
        all_tokens = {name: self.issue(name + "-chatgpt") for name in ("ynab", "notoli", "macromapper")}
        for caller, secret in (("notoli", self.secret), ("macromapper", self.macro_secret)):
            header = "Basic " + base64.b64encode((caller + "-introspection:" + secret).encode()).decode()
            for target, tokens in all_tokens.items():
                response = self.client.post("/o/introspect/", urlencode({"token": tokens["access_token"]}),
                    content_type="application/x-www-form-urlencoded", secure=True, HTTP_AUTHORIZATION=header)
                self.assertEqual(response.json()["active"], caller == target)
            forbidden = self.client.post("/o/token/", "grant_type=client_credentials", secure=True,
                content_type="application/x-www-form-urlencoded", HTTP_AUTHORIZATION=header)
            self.assertEqual(forbidden.status_code, 400)
        for name, tokens in all_tokens.items():
            for target in ("ynab", "notoli", "macromapper"):
                if name != target:
                    self.assertEqual(self.post_token(grant_type="refresh_token", client_id=target + "-chatgpt",
                        refresh_token=tokens["refresh_token"]).status_code, 400)

    def test_consent_csrf_grant_management_and_metadata(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        self.assertEqual(strict.post("/o/authorize/", self.authorization(), secure=True).status_code, 403)
        tokens = self.issue()
        self.assertEqual(self.browser.get("/o/authorize/", self.authorization(approval_prompt="auto"), secure=True).status_code, 400)
        listing = self.browser.get("/o/authorized_tokens/", secure=True)
        self.assertEqual(listing.status_code, 200)
        self.assertNotContains(listing, tokens["access_token"])
        token_id = AccessToken.objects.get().pk
        self.browser.force_login(self.other)
        self.assertEqual(self.browser.post(f"/o/authorized_tokens/{token_id}/delete/", secure=True).status_code, 404)
        self.browser.force_login(self.owner)
        self.assertEqual(self.browser.post(f"/o/authorized_tokens/{token_id}/delete/", secure=True).status_code, 302)
        self.assertFalse(self.introspect(tokens["access_token"]).json()["active"])
        metadata = self.client.get("/.well-known/oauth-authorization-server", secure=True).json()
        self.assertEqual(metadata["issuer"], settings.ISSUER)
        self.assertEqual(metadata["code_challenge_methods_supported"], ["S256"])
        self.assertEqual(metadata["token_endpoint_auth_methods_supported"], ["none"])
        self.assertEqual(metadata["introspection_endpoint_auth_methods_supported"], ["client_secret_basic"])
        self.assertNotIn("registration_endpoint", metadata)
        self.assertEqual(self.client.get("/o/applications/", secure=True).status_code, 404)

    def test_closed_login_and_actual_csrf_consent_form(self):
        class Inputs(HTMLParser):
            def __init__(self, content):
                super().__init__()
                self.values = {}
                self.feed(content.decode())

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "input" and attrs.get("name"):
                    self.values[attrs["name"]] = attrs.get("value", "")

        browser = Client(enforce_csrf_checks=True)
        login = browser.get("/accounts/login/", secure=True)
        fields = Inputs(login.content).values
        fields.update(username="synthetic-owner", password="synthetic-password")
        self.assertEqual(browser.post("/accounts/login/", fields, secure=True, HTTP_REFERER=settings.ISSUER + "/accounts/login/").status_code, 302)
        response = browser.get("/o/authorize/", self.authorization(), secure=True)
        self.assertEqual(response.status_code, 200)
        fields = Inputs(response.content).values
        fields["allow"] = "Authorize"
        self.assertEqual(browser.post(
            "/o/authorize/", fields, secure=True,
            HTTP_ORIGIN="https://untrusted.example",
            HTTP_REFERER="https://untrusted.example/consent",
        ).status_code, 403)
        granted = browser.post("/o/authorize/", fields, secure=True, HTTP_REFERER=settings.ISSUER + "/o/authorize/")
        self.assertEqual(granted.status_code, 302)
        self.assertIn("code=", granted["Location"])
        self.assertEqual(browser.get("/accounts/signup/", secure=True).status_code, 404)

    def test_loopback_and_key_rotation_restore_invalidation(self):
        code, callback = self.code("ynab-codex", redirect_uri="http://127.0.0.1:49181/callback")
        self.assertEqual(self.post_token(grant_type="authorization_code", client_id="ynab-codex", code=code,
                         redirect_uri=callback, code_verifier=self.verifier).status_code, 200)
        self.assertTrue(valid_callback("http://[::1]:4581/callback"))
        self.assertFalse(valid_callback("http://localhost/callback"))
        self.assertFalse(valid_callback("https://client.example/callback#fragment"))
        tokens = self.issue()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        with override_settings(SIGNING_PRIVATE_KEY=pem, SIGNING_KEY_ID="synthetic-key-2"):
            self.assertFalse(self.introspect(tokens["access_token"]).json()["active"])
            new = self.issue()
            jwt.decode(new["access_token"], key.public_key(), algorithms=["RS256"], audience=settings.NOTOLI_RESOURCE)
        self.code()
        self.assertTrue(Session.objects.exists())
        call_command("revoke_all_mcp_grants", stdout=StringIO())
        for model in (AccessToken, RefreshToken, Grant, Session):
            self.assertFalse(model.objects.exists())

    def test_expiry_and_resource_narrowing_fail_closed(self):
        code, callback = self.code()
        Grant.objects.filter(code=code).update(expires=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.post_token(grant_type="authorization_code", client_id="notoli-chatgpt", code=code,
                         redirect_uri=callback, code_verifier=self.verifier).status_code, 400)
        tokens = self.issue()
        self.assertEqual(self.post_token(grant_type="refresh_token", client_id="notoli-chatgpt",
                         refresh_token=tokens["refresh_token"], resource=settings.YNAB_RESOURCE).status_code, 400)
        AccessToken.objects.update(expires=timezone.now() - timedelta(days=31))
        self.assertEqual(self.post_token(grant_type="refresh_token", client_id="notoli-chatgpt",
                         refresh_token=tokens["refresh_token"]).status_code, 400)

    def test_closed_management_registration_and_single_ynab_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            subject = Path(directory) / "new-subject"
            with patch("auth_service.management.commands.bootstrap_mcp_owner.protected_text", return_value="synthetic-long-owner-password-9174"):
                call_command("bootstrap_mcp_owner", username="new-owner", password_file="synthetic", subject_output=str(subject), stdout=StringIO())
            owner = User.objects.get(pk=subject.read_text().strip())
            self.assertTrue(owner.check_password("synthetic-long-owner-password-9174"))
            with self.assertRaises(CommandError):
                call_command("bootstrap_mcp_owner", username="new-owner", password_file="synthetic", subject_output=str(subject), stdout=StringIO())
        with self.assertRaises(ValidationError):
            policy = self.apps["ynab-codex"].mcp_policy
            policy.allowed_user = self.other
            policy.full_clean()
        with self.assertRaises(CommandError):
            call_command("register_issuer_client", resource="ynab", client="chatgpt", owner_subject=str(self.owner.pk),
                         redirect_uri=["https://client.example/callback"], stdout=StringIO())
        new_secret = "synthetic-rotated-introspection-credential" * 2
        with patch("auth_service.management.commands.register_mcp_introspector.protected_text", return_value=new_secret):
            call_command("register_mcp_introspector", resource="notoli", secret_file="synthetic", rotate=True, stdout=StringIO())
        self.assertEqual(self.introspect("unknown").status_code, 401)

    def test_readiness_fails_closed(self):
        self.assertEqual(self.client.get("/health/ready").status_code, 200)
        with patch("auth_service.views.connection.cursor", side_effect=RuntimeError("synthetic")):
            response = self.client.get("/health/ready")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"status": "unavailable"})


class InitialReadiness(TestCase):
    def test_migrated_empty_issuer_is_ready_before_closed_owner_bootstrap(self):
        self.assertFalse(User.objects.exists())
        self.assertFalse(Application.objects.exists())
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready"})
        with patch("auth_service.views.signing_key", side_effect=ValueError("synthetic")):
            self.assertEqual(self.client.get("/health/ready").status_code, 503)


class RestartPersistence(TransactionTestCase):
    authorization = Flows.authorization
    code = Flows.code
    post_token = Flows.post_token
    issue = Flows.issue

    def setUp(self):
        Flows.setUpTestData.__func__(type(self))
        Flows.setUp(self)

    def test_refresh_survives_new_process_and_revocation_does_not_resurrect(self):
        token = self.issue()
        env = dict(os.environ, MCP_AUTH_TEST_DB_PATH=str(connection.settings_dict["NAME"]))
        connection.close()
        source = """
import django, json, sys
django.setup()
from django.test import Client
from urllib.parse import urlencode
data=json.load(sys.stdin)
result=Client().post('/o/token/', urlencode(data), content_type='application/x-www-form-urlencoded', secure=True)
print(json.dumps({'status':result.status_code, 'has_refresh':bool(result.json().get('refresh_token'))}))
"""
        import json
        data = json.dumps(dict(grant_type="refresh_token", client_id="notoli-chatgpt", refresh_token=token["refresh_token"]))
        result = subprocess.run([sys.executable, "-c", source], input=data, env=env, text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout), {"status": 200, "has_refresh": True})
        call_command("revoke_all_mcp_grants", stdout=StringIO())
        connection.close()
        result = subprocess.run([sys.executable, "-c", source], input=data, env=env, text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout), {"status": 400, "has_refresh": False})
