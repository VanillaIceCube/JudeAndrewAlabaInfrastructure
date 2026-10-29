"""Credential-free HTTP/stdio acceptance inside the disposable, networkless image.

Fixture tools and write-factory options are mounted test code, never image code.
"""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import io
import json
import logging
import os
from pathlib import Path
import signal
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastmcp.client.transports import StdioTransport
from fastmcp.server.auth.providers.jwt import RSAKeyPair
from joserfc import jwk, jwt
from starlette.testclient import TestClient
import gateway as g

ROOT = Path(__file__).resolve().parents[2]


class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pair = RSAKeyPair.generate()
        cls.key = jwk.import_key(cls.pair.private_key.get_secret_value(), "RSA")
        cls.identity = g.Identity("https://issuer.fixture.example", "owner-fixture",
                                 frozenset({"client-a", "client-b"}), cls.pair.public_key)

    def transport(self, preview=False, missing=False):
        return StdioTransport("/usr/local/bin/node", [
            "/missing-child" if missing else str(ROOT / "experiments/ynab-mcp/fake-child.mjs"),
            "/app", *( ["synthetic-preview-tests"] if preview else [])],
            env={"YNAB_ALLOW_WRITES": "0"}, keep_alive=False, log_file=Path(os.devnull))

    def token(self, client="client-a", changes=None, header=None):
        now = int(time.time())
        claims = {"iss": self.identity.issuer, "sub": self.identity.owner,
                  "client_id": client, "aud": g.RESOURCE, "iat": now, "exp": now + 300,
                  "scope": "ynab:read"}
        claims.update(changes or {})
        return jwt.encode(header or {"alg": "RS256", "typ": "at+jwt"}, claims, self.key, algorithms=["RS256"])

    @contextlib.contextmanager
    def running(self, preview=False, missing=False):
        self.app = g.Gateway(self.identity, lambda: self.transport(preview, missing))
        self.number = 0
        with TestClient(self.app, base_url=g.ORIGIN) as self.http:
            yield self.http

    def headers(self, sid=None, token=None):
        return {"authorization": "Bearer " + (token or self.token()),
                "accept": "application/json, text/event-stream",
                **({"mcp-session-id": sid, "mcp-protocol-version": g.PROTOCOL} if sid else {})}

    def rpc(self, method, params=None, sid=None, token=None, rpc_id=None, **kwargs):
        self.number += 1
        # Most tests isolate a security control from rate limiting; its own test
        # below leaves the bucket untouched. This changes no production setting.
        self.app.credit = 5
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not isinstance(method, str) or not method.startswith("notifications/"):
            payload["id"] = self.number if rpc_id is None else rpc_id
        return self.http.post("/mcp", headers=self.headers(sid, token), json=payload, **kwargs)

    def initialize(self, token=None):
        response = self.rpc("initialize", {"protocolVersion": g.PROTOCOL, "capabilities": {},
                                          "clientInfo": {"name": "fixture", "version": "1"}}, token=token)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["result"]["protocolVersion"], g.PROTOCOL)
        sid = response.headers["mcp-session-id"]
        self.assertEqual(self.rpc("notifications/initialized", sid=sid, token=token).status_code, 202)
        return sid

    def call(self, sid, name, args=None):
        return self.rpc("tools/call", {"name": name, "arguments": args or {}}, sid=sid)

    @staticmethod
    def content(response):
        result = response.json()["result"]
        return result.get("structuredContent", {}).get("result") or json.loads(result["content"][0]["text"])

    def test_authenticated_upstream_read_only_discovery_and_call(self):
        self.assertEqual(Path(g.__file__).parent, Path("/gateway"))
        with self.running():
            sid = self.initialize()
            response = self.rpc("tools/list", sid=sid)
            names = {tool["name"] for tool in response.json()["result"]["tools"]}
            self.assertIn("list_budgets", names)
            self.assertLessEqual(names, g.READ_TOOLS)
            self.assertFalse(names & {"create_payee", "preview_write_tool", "ynab_tool_execute", "ynab_auth_status", "fixture_status"})
            for method, field in (("resources/list", "resources"), ("resources/templates/list", "resourceTemplates"), ("prompts/list", "prompts")):
                self.assertEqual(self.rpc(method, sid=sid).json()["result"][field], [])
            self.assertEqual(self.content(self.call(sid, "list_budgets"))["budgets"][0]["name"], "Synthetic budget")
            for tool in ("create_payee", "preview_write_tool", "ynab_tool_execute", "ynab_write_tool_execute"):
                self.assertEqual(self.call(sid, tool).status_code, 403)

    def test_anonymous_expired_wrong_identity_scope_and_malformed_tokens(self):
        with self.running():
            self.assertEqual(self.http.post("/mcp", json={}).status_code, 401)
            self.assertIn(g.METADATA, self.http.post("/mcp", json={}).headers["www-authenticate"])
            for claims in ({"exp": 1}, {"exp": None}, {"iat": None}, {"exp": True},
                           {"exp": int(time.time()) + 1000}, {"iat": int(time.time()) + 100},
                           {"nbf": int(time.time()) + 100}, {"sub": "other"},
                           {"client_id": "unknown"}, {"client_id": ["client-a"]},
                           {"azp": "other"}, {"iss": "https://other.example"},
                           {"aud": "https://other.example/mcp"}):
                with self.subTest(claims=claims):
                    response = self.rpc("tools/list", token=self.token(changes=claims))
                    self.assertEqual(response.status_code, 401)
            self.assertEqual(self.rpc("tools/list", token=self.token(changes={"scope": "ynab:write"})).status_code, 403)
            self.assertEqual(self.rpc("tools/list", token="malformed").status_code, 401)
            self.assertEqual(self.rpc("tools/list", token=self.token(header={"alg": "RS256", "typ": "JWT"})).status_code, 401)
            self.assertEqual(self.app.sessions, {})

    def test_managed_provider_audiences_remain_resource_and_principal_bound(self):
        userinfo = self.identity.issuer.rstrip("/") + "/userinfo"
        with self.running():
            for client in ("client-a", "client-b"):
                for audience in (g.RESOURCE, [g.RESOURCE], [g.RESOURCE, userinfo], [userinfo, g.RESOURCE]):
                    token = self.token(client, {"aud": audience, "scope": "openid ynab:read"})
                    sid = self.initialize(token)
                    self.assertEqual(self.rpc("tools/list", sid=sid, token=token).status_code, 200)
                    self.app.credit = 5
                    self.assertEqual(self.http.delete("/mcp", headers=self.headers(sid, token)).status_code, 200)
            for audience in ([], [userinfo], [g.RESOURCE, g.RESOURCE],
                             [g.RESOURCE, "https://another-app.example/mcp"],
                             [g.RESOURCE, "https://other-issuer.example/userinfo"],
                             [g.RESOURCE, userinfo, "https://another-app.example/mcp"],
                             [g.RESOURCE, 42], {"resource": g.RESOURCE}):
                with self.subTest(audience=audience):
                    self.assertEqual(self.rpc("initialize", token=self.token(changes={"aud": audience})).status_code, 401)
            for claims in ({"sub": "another-owner"}, {"client_id": "another-app-client"}, {"exp": int(time.time()) + 1000}):
                self.assertEqual(self.rpc("initialize", token=self.token(changes={"aud": [g.RESOURCE, userinfo], **claims})).status_code, 401)

    def test_principal_bound_session_rotation_delete_and_replay(self):
        with self.running():
            sid = self.initialize()
            self.app.credit = 5
            missing = self.http.delete("/mcp", headers={**self.headers(), "mcp-protocol-version": g.PROTOCOL})
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(self.rpc("tools/list", sid=sid, token=self.token("client-b")).status_code, 404)
            self.assertEqual(self.rpc("tools/list", sid=sid, rpc_id="unique").status_code, 200)
            self.assertEqual(self.rpc("tools/list", sid=sid, rpc_id="unique").status_code, 409)
            # New bearer for the same principal is accepted; it cannot transfer sessions.
            self.assertEqual(self.rpc("tools/list", sid=sid, token=self.token()).status_code, 200)
            self.app.credit = 5
            self.assertEqual(self.http.delete("/mcp", headers=self.headers(sid)).status_code, 200)
            self.assertEqual(self.rpc("tools/list", sid=sid).status_code, 404)

    def test_host_origin_exact_paths_forwarded_headers_and_safe_errors(self):
        captured = io.StringIO()
        handler = logging.StreamHandler(captured)
        logging.getLogger().addHandler(handler)
        try:
            with self.running():
                self.assertEqual(self.http.get(g.METADATA).json()["resource"], g.RESOURCE)
                for path in ("/mcp/", "/%6dcp", "/mcp?access_token=private-sentinel", "/sse", "/auth/mcp/authorize"):
                    self.assertEqual(self.http.post(path, headers=self.headers(), json={}).status_code, 404)
                for headers in ({"host": "evil.example"}, {"origin": "https://evil.example"}, {"origin": "null"}):
                    self.assertEqual(self.http.post("/mcp", headers={**self.headers(), **headers}, json={}).status_code, 403)
                self.assertEqual(self.http.post("/mcp", headers={"x-api-key": self.token(), "x-forwarded-user": "owner-fixture"}, json={}).status_code, 401)
                sid = self.initialize()
                auth_case = self.http.post("/mcp", headers={**self.headers(sid), "authorization": "bEaReR   " + self.token()},
                    json={"jsonrpc": "2.0", "id": 998, "method": "tools/list"})
                self.assertEqual(auth_case.status_code, 200)
                response = self.http.post("/mcp", headers={**self.headers(sid), "x-forwarded-host": "evil.example",
                    "x-forwarded-proto": "http", "x-forwarded-for": "evil", "forwarded": "host=evil.example"},
                    json={"jsonrpc": "2.0", "id": 999, "method": "tools/list"})
                self.assertEqual(response.status_code, 200)
                error = self.call(sid, "get_budget", {"budgetId": "private-sentinel"})
                self.assertIn("error", error.json())
                self.assertNotIn("private-sentinel", error.text)
                self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(captured.getvalue(), "")
        finally:
            logging.getLogger().removeHandler(handler)

    def test_size_rate_session_and_concurrency_limits(self):
        with self.running():
            response = self.http.post("/mcp", headers={**self.headers(), "content-type": "application/json"}, content=" " * 262145)
            self.assertEqual(response.status_code, 413)
            self.assertEqual(self.http.post("/mcp", headers={**self.headers(), "content-type": "application/json"}, content="{broken").status_code, 400)
            first = self.initialize()
            second = self.initialize(self.token("client-b"))
            self.assertNotEqual(first, second)
            self.assertEqual(self.rpc("initialize", {"protocolVersion": g.PROTOCOL}).status_code, 429)
            self.app.credit = 0
            self.app.rate_updated = time.monotonic()
            self.assertEqual(self.http.post("/mcp", headers=self.headers(first), json={}).status_code, 429)
            self.app.credit, self.app.inflight = 5, 4
            self.assertEqual(self.http.post("/mcp", headers=self.headers(first), json={}).status_code, 429)
            self.app.inflight = 0
            self.app.sessions[first].touched -= 601
            self.assertEqual(self.rpc("tools/list", sid=first).status_code, 404)

    def test_public_admission_limit_precedes_signature_verification(self):
        with self.running(), patch.object(self.app.verifier, "verify_token", new_callable=AsyncMock) as verify:
            verify.return_value = None
            for _ in range(5):
                response = self.http.post("/mcp", headers=self.headers(), content="{broken")
                self.assertEqual(response.status_code, 401)
            self.assertEqual(self.http.post("/mcp", headers=self.headers(), content="{broken").status_code, 429)
            self.assertEqual(verify.await_count, 5)

    def test_malformed_rpc_fields_reject_without_killing_the_owned_session(self):
        with self.running():
            sid = self.initialize()
            for malformed in ([], {}, None, 42):
                with self.subTest(malformed=malformed):
                    self.assertEqual(self.rpc(malformed, sid=sid).status_code, 400)
                    self.assertEqual(self.rpc("tools/call", {"name": malformed}, sid=sid).status_code, 400)
                    self.assertEqual(self.rpc("tools/list", sid=sid).status_code, 200)

    def test_chunked_error_is_redacted_before_headers_and_invalid_output_is_safe(self):
        async def chunked(_scope, _receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
            raw = b'{"jsonrpc":"2.0","id":123,"error":{"message":"private-sentinel"}}'
            await send({"type": "http.response.body", "body": raw[:25], "more_body": True})
            await send({"type": "http.response.body", "body": raw[25:]})
        async def invalid(_scope, _receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"private-sentinel"})
        with self.running():
            sid = self.initialize()
            with patch.object(self.app, "app", chunked):
                response = self.rpc("tools/list", sid=sid)
                self.assertEqual(response.status_code, 200)
                self.assertIn("error", response.json())
                self.assertNotIn("private-sentinel", response.text)
            with patch.object(self.app, "app", invalid):
                response = self.rpc("tools/list", sid=sid)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("private-sentinel", response.text)

    def test_session_children_are_distinct_stable_and_death_cannot_reconnect(self):
        with patch.object(g, "READ_TOOLS", g.READ_TOOLS | {"fixture_status"}), self.running():
            a, b = self.initialize(), self.initialize(self.token("client-b"))
            status_a = self.content(self.call(a, "fixture_status"))
            status_a_again = self.content(self.call(a, "fixture_status"))
            response_b = self.rpc("tools/call", {"name": "fixture_status", "arguments": {}}, sid=b, token=self.token("client-b"))
            pid = status_a["pid"]
            self.assertEqual(pid, status_a_again["pid"])
            self.assertNotEqual(pid, self.content(response_b)["pid"])
            # PID comes from our synthetic child in this disposable networkless container.
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.1)
            self.assertEqual(self.rpc("tools/list", sid=a).status_code, 404)
            self.assertEqual(self.rpc("tools/list", sid=a).status_code, 404)
            self.assertEqual(self.rpc("tools/list", sid=b, token=self.token("client-b")).status_code, 200)

    def test_readiness_missing_child_and_token_are_not_plain_health_success(self):
        with self.running(missing=True):
            with TestClient(self.app, base_url=g.ORIGIN, client=("127.0.0.1", 1234)) as private:
                self.assertEqual(private.get("/health/live").status_code, 200)
                self.assertEqual(private.get("/health/ready").status_code, 503)
            self.assertEqual(self.http.get("/health/ready").status_code, 404)
        # The real policy cannot start without a token file; never contact YNAB.
        app = g.Gateway(self.identity, g.child_transport)
        with TestClient(app, base_url=g.ORIGIN, client=("127.0.0.1", 1234)) as private:
            self.assertEqual(private.get("/health/ready").status_code, 503)
        healthy = g.Gateway(self.identity, self.transport)
        with TestClient(healthy, base_url=g.ORIGIN, client=("127.0.0.1", 1234)) as private:
            self.assertEqual(private.get("/health/ready").status_code, 200)

    def test_identity_files_are_private_regular_and_public_key_only(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            identity_file = directory / "gateway_identity.json"
            key_file = directory / "oauth_public_key.pem"
            token_file = directory / "ynab_api_token"
            identity_file.write_text(json.dumps({"issuer": self.identity.issuer, "owner": self.identity.owner,
                                                 "clients": list(self.identity.clients)}))
            key_file.write_text(self.pair.public_key)
            token_file.write_text("synthetic-fixture-only")
            identity_file.chmod(0o400)
            key_file.chmod(0o400)
            token_file.chmod(0o400)
            self.assertIsInstance(g.from_config(directory), g.Gateway)
            identity_file.chmod(0o644)
            with self.assertRaises(ValueError):
                g.from_config(directory)

            identity_file.chmod(0o400)
            with patch.dict(os.environ, {"YNAB_ALLOW_WRITES": "1"}), self.assertRaises(ValueError):
                g.from_config(directory)
            key_file.chmod(0o600)
            key_file.write_text(self.pair.private_key.get_secret_value())
            key_file.chmod(0o400)
            with self.assertRaises(ValueError):
                g.from_config(directory)

    def test_startup_rejects_invalid_token_metadata_before_constructing_gateway(self):
        import stat
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "gateway_identity.json").write_text(json.dumps({"issuer": self.identity.issuer,
                "owner": self.identity.owner, "clients": list(self.identity.clients)}))
            (directory / "oauth_public_key.pem").write_text(self.pair.public_key)
            token = directory / "ynab_api_token"
            token.write_text("synthetic-fixture-only")
            for file in directory.iterdir():
                file.chmod(0o400)
            with patch.object(g, "Gateway") as constructor:
                token.chmod(0o644)
                with self.assertRaises(ValueError):
                    g.from_config(directory)
                token.chmod(0o600)
                token.write_text("")
                token.chmod(0o400)
                with self.assertRaises(ValueError):
                    g.from_config(directory)
                token.chmod(0o600)
                token.write_text("x" * 4097)
                token.chmod(0o400)
                with self.assertRaises(ValueError):
                    g.from_config(directory)
                token.unlink()
                token.mkdir()
                with self.assertRaises(ValueError):
                    g.from_config(directory)
                token.rmdir()
                token.symlink_to(directory / "oauth_public_key.pem")
                with self.assertRaises(ValueError):
                    g.from_config(directory)
                token.unlink()
                token.write_text("synthetic-fixture-only")
                token.chmod(0o400)
                original = Path.lstat
                def wrong_owner(path):
                    if path == token:
                        return SimpleNamespace(st_mode=stat.S_IFREG | 0o400, st_uid=0, st_size=22)
                    return original(path)
                # The container intentionally lacks CAP_CHOWN. Actual wrong-uid
                # mounts are also exercised by #58's runtime Docker suite.
                with patch.object(Path, "lstat", wrong_owner), self.assertRaises(ValueError):
                    g.from_config(directory)
                constructor.assert_not_called()
    def test_preview_tokens_remain_process_local_single_use_and_expiring(self):
        # This synthetic factory option is not a gateway setting or YNAB_ALLOW_WRITES=1.
        additional = {"preview_write_tool", "create_payee", "fixture_expire"}
        with patch.object(g, "READ_TOOLS", g.READ_TOOLS | additional), self.running(preview=True):
            a = self.initialize()
            b = self.initialize(self.token("client-b"))
            args = {"budgetId": "fixture-budget", "name": "Synthetic payee"}
            preview = self.content(self.call(a, "preview_write_tool", {"tool_name": "create_payee", "input": args}))
            preview_token = preview["preview_token"]
            request = {**args, "confirmed": True, "previewToken": preview_token}
            cross = self.rpc("tools/call", {"name": "create_payee", "arguments": request}, sid=b, token=self.token("client-b"))
            self.assertIn("error", cross.json())
            self.assertIn("error", self.call(a, "create_payee", {**request, "confirmed": False}).json())
            self.assertNotIn("error", self.call(a, "create_payee", request).json())
            self.assertIn("error", self.call(a, "create_payee", request).json())
            changed = self.content(self.call(a, "preview_write_tool", {"tool_name": "create_payee", "input": args}))
            self.assertIn("error", self.call(a, "create_payee", {**args, "name": "Changed", "confirmed": True, "previewToken": changed["preview_token"]}).json())
            self.assertIn("error", self.call(a, "create_payee", {**args, "confirmed": True, "previewToken": changed["preview_token"]}).json())
            next_preview = self.content(self.call(a, "preview_write_tool", {"tool_name": "create_payee", "input": args}))
            self.call(a, "fixture_expire")
            self.assertIn("error", self.call(a, "create_payee", {**args, "confirmed": True, "previewToken": next_preview["preview_token"]}).json())

    def test_inflight_token_expiry_invalidates_the_session_without_retry(self):
        with patch.object(g, "READ_TOOLS", g.READ_TOOLS | {"fixture_wait"}), self.running():
            sid = self.initialize()
            response = self.rpc("tools/call", {"name": "fixture_wait", "arguments": {}}, sid=sid,
                                token=self.token(changes={"exp": int(time.time()) + 2}))
            self.assertEqual(response.status_code, 503)
            self.assertEqual(self.rpc("tools/list", sid=sid).status_code, 404)

    def test_concurrent_call_and_cancellation_keep_the_same_child(self):
        with patch.object(g, "READ_TOOLS", g.READ_TOOLS | {"fixture_wait", "fixture_status"}), self.running():
            sid = self.initialize()
            before = self.content(self.call(sid, "fixture_status"))
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.rpc, "tools/call", {"name": "fixture_wait", "arguments": {}}, sid, None, "long-call")
                for _ in range(30):
                    state = self.content(self.call(sid, "fixture_status"))
                    if state["waiting"]:
                        break
                    time.sleep(0.05)
                self.assertEqual(state["waiting"], 1)
                cancel = self.rpc("notifications/cancelled", {"requestId": "long-call"}, sid=sid)
                self.assertEqual(cancel.status_code, 202)
                future.result(timeout=5)
            after = self.content(self.call(sid, "fixture_status"))
            self.assertEqual(before["pid"], after["pid"])
            self.assertEqual(after["cancelled"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
