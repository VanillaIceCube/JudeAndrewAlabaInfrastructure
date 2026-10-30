"""Owner-only, scope-bound policy around the pinned, maintained MCP proxy.

No OAuth authorization server, protocol engine, Docker socket or caller-selected
upstream. The inner SDK owns MCP negotiation, sessions, stdio and cancellation.
"""
import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import re
import stat
import time
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.providers.proxy import FastMCPProxy, StatefulProxyClient
from fastmcp.server.transforms import Visibility
from fastmcp.utilities.auth import decode_jwt_header

ORIGIN = "https://ynab.judeandrewalaba.com"
RESOURCE = ORIGIN + "/mcp"
METADATA = "/.well-known/oauth-protected-resource/mcp"
PROTOCOL = "2025-11-25"
READ_TOOLS = frozenset("""
get_user list_budgets get_budget get_budget_settings list_accounts get_account
list_categories get_category get_month_category list_payees get_payee
list_payee_locations get_payee_location get_payee_locations_by_payee list_months
get_month list_money_movements get_money_movements_by_month list_money_movement_groups
get_money_movement_groups_by_month get_transactions search_transactions get_transaction
list_scheduled_transactions get_scheduled_transaction search_categories search_payees
review_unapproved get_overspent_categories audit_credit_card_payments
audit_account_reconciliation get_income_expense_summary detect_recurring_charges
get_budget_health get_spending_trends forecast_scheduled_balances
resolve_matched_transactions export_transactions suggest_transaction_categories
ynab_auth_status ynab_tool_index ynab_tool_execute list_undo_history list_operations
""".split())
# Exact pinned upstream catalog. Generic dispatch never bypasses this boundary.
WRITE_TOOLS = frozenset("""
preview_write_tool create_account update_month_category update_category create_category
create_category_group update_category_group update_payee create_payee create_transaction
create_transactions update_transaction delete_transaction update_transactions
approve_transactions reassign_payee_transactions ynab_write_tool_execute import_transactions
create_scheduled_transaction update_scheduled_transaction delete_scheduled_transaction
move_category_budget resume_operation merge_category retire_category
prepare_split_for_matching undo_operation
""".split())
RESOURCES = frozenset("ynab://guide/" + name for name in
                      ("methodology", "write-safety", "audit-patterns", "flags-reference"))
PROMPTS = frozenset(("monthly-review", "weekly-triage", "categorize-and-approve",
                     "subscription-audit", "reconcile-account", "credit-card-audit"))
CURRENT_SESSION = ContextVar("ynab_session", default=None)


@dataclass(frozen=True)
class Identity:
    issuer: str
    owner: str
    clients: frozenset[str]
    public_key: str

    def __post_init__(self):
        url = urlsplit(self.issuer)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment or not isinstance(self.owner, str) or not self.owner or not self.clients
                or len(self.clients) > 8 or any(not isinstance(c, str) or not c for c in self.clients)):
            raise ValueError("Invalid gateway identity configuration")
        key = load_pem_public_key(self.public_key.encode())
        if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
            raise ValueError("Invalid verification public key")


class OwnerVerifier(JWTVerifier):
    def __init__(self, identity):
        super().__init__(public_key=identity.public_key, issuer=identity.issuer,
                         audience=RESOURCE, algorithm="RS256", required_scopes=[])
        self.identity = identity

    async def load_access_token(self, token):
        access = await super().load_access_token(token)
        if access is None:
            return None
        claims, now = access.claims, time.time()
        exp, issued = claims.get("exp"), claims.get("iat")
        client_id = claims.get("client_id")
        if (type(exp) is not int or type(issued) is not int or not issued <= now + 5
                or not now < exp <= issued + 900 or claims.get("aud") != RESOURCE
                or claims.get("sub") != self.identity.owner
                or not isinstance(client_id, str) or client_id not in self.identity.clients
                or claims.get("azp", client_id) != client_id
                or decode_jwt_header(token).get("typ") != "at+jwt"):
            return None
        if "nbf" in claims and (type(claims["nbf"]) is not int or claims["nbf"] > now):
            return None
        access.resource = RESOURCE
        access.subject = self.identity.owner
        return access


@dataclass
class Session:
    principal: tuple
    touched: float
    writes: bool = False
    client: object = None
    backend: object = None
    connected: bool = False
    dead: bool = False
    ids: set = field(default_factory=set)


def child_transport(writes=False, *, persistent=False):
    """Fixed app command and minimal environment; no HOME/config/token inheritance."""
    return StdioTransport(command="/usr/local/bin/node", args=["--use-env-proxy", "/policy/entrypoint.mjs"],
                          cwd="/app", env={"PATH": "/usr/local/bin:/usr/bin:/bin",
                          "HOME": "/data" if persistent else "/tmp", "YNAB_API_TOKEN_FILE": "/run/secrets/ynab_api_token",
                          "YNAB_ALLOW_WRITES": "1" if writes else "0", "YNAB_DISABLE_AGENT_CONFIG_FALLBACK": "1",
                          "HTTPS_PROXY": "http://ynab-egress:3128", "HTTP_PROXY": "http://ynab-egress:3128",
                          "NO_PROXY": ""},
                          log_file=Path(os.devnull), keep_alive=False)


class Gateway:
    def __init__(self, identity, transport=None, *, allow_writes=False):
        # Upstream auth/transport logs can include client/claim or child details.
        # All production diagnostics are status categories only, via health.
        logging.disable(logging.CRITICAL)
        if type(allow_writes) is not bool:
            raise ValueError("Invalid gateway write policy")
        self.identity = identity
        self.allow_writes = allow_writes
        self.verifier = OwnerVerifier(identity)
        self.sessions = {}
        self.pending = 0
        self.inflight = 0
        self.credit = 5.0
        self.rate_updated = time.monotonic()
        self.transport_factory = transport or (lambda writes=False: child_transport(writes, persistent=allow_writes))
        auth = RemoteAuthProvider(self.verifier, authorization_servers=[identity.issuer],
                                  base_url=ORIGIN, scopes_supported=["ynab:read", *(["ynab:write"] if allow_writes else [])],
                                  challenge_scopes=["ynab:read"])
        self.proxy = FastMCPProxy(client_factory=self.client_factory, name="YNAB",
                                  auth=auth, provider_error_strategy="raise")
        self.proxy.add_transform(Visibility(False, match_all=True))
        self.proxy.add_transform(Visibility(True, names=READ_TOOLS | (WRITE_TOOLS if allow_writes else set()), components={"tool"}))
        self.proxy.add_transform(Visibility(True, names=RESOURCES, components={"resource"}))
        self.proxy.add_transform(Visibility(True, names=PROMPTS, components={"prompt"}))
        self.app = self.proxy.http_app(path="/mcp", json_response=True, stateless_http=False,
                                       session_idle_timeout=600, allowed_hosts=[urlsplit(ORIGIN).netloc],
                                       allowed_origins=[ORIGIN])
        self.ready_at, self.ready = 0, False

    def client_factory(self):
        session = CURRENT_SESSION.get()
        if session is None or session.dead:
            raise RuntimeError("Upstream session unavailable")
        # Client.new() shares its transport. Create a distinct transport factory
        # per remote session so even maintained client clones cannot share stdio.
        if session.backend is None:
            session.backend = StatefulProxyClient(self.transport_factory(session.writes), mode="legacy", timeout=25,
                                                  forward_incoming_headers=False)
        client = session.backend.new_stateful()
        if session.client is not None and (client is not session.client
                                           or session.connected and not client.is_connected()):
            session.dead = True
            raise RuntimeError("Upstream session unavailable")
        session.client = client
        return client

    async def respond(self, send, status, payload=None, extra=()):
        if status == 401 and not any(key == b"www-authenticate" for key, _ in extra):
            extra = [*extra, (b"www-authenticate", f'Bearer resource_metadata="{ORIGIN}{METADATA}"'.encode())]
        body = json.dumps(payload if payload is not None else {"error": "request_rejected"}).encode()
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", b"application/json"), (b"cache-control", b"no-store"),
            (b"x-content-type-options", b"nosniff"), *extra]})
        await send({"type": "http.response.body", "body": body})

    async def readiness(self):
        if time.monotonic() - self.ready_at > 10:
            self.ready_at, self.ready = time.monotonic(), False
            try:
                async with asyncio.timeout(5), Client(self.transport_factory(self.allow_writes), mode="legacy", timeout=4) as client:
                    tools = await client.list_tools()
                    result = await client.call_tool("ynab_auth_status", {})
                    structured = result.structured_content or {}
                    status = structured.get("result") or json.loads(result.content[0].text)
                    self.ready = ("list_budgets" in {tool.name for tool in tools}
                                  and status.get("authenticated") is True
                                  and status.get("writes_enabled") is self.allow_writes
                                  and (not self.allow_writes or WRITE_TOOLS <= {tool.name for tool in tools}))
            except Exception:
                # Keep readiness false; raw child/configuration errors are private.
                pass
        return self.ready

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {}
        for key, value in scope.get("headers", []):
            key = key.lower()
            if key in headers and key in {b"authorization", b"host", b"origin", b"mcp-session-id", b"content-length"}:
                return await self.respond(send, 400)
            headers[key] = value
        if sum(len(k) + len(v) for k, v in scope.get("headers", [])) > 16384:
            return await self.respond(send, 431)
        path, method = scope["path"], scope["method"]
        # Health has no data/identity; it is loopback-only and never routed by ingress.
        if path in {"/health/live", "/health/ready"}:
            if scope.get("client", (None,))[0] not in {"127.0.0.1", "::1"} or method != "GET":
                return await self.respond(send, 404)
            ready = path == "/health/live" or await self.readiness()
            return await self.respond(send, 200 if ready else 503, {"ready": ready})
        if (headers.get(b"host") != urlsplit(ORIGIN).netloc.encode()
                or headers.get(b"origin", ORIGIN.encode()) != ORIGIN.encode()):
            return await self.respond(send, 403)
        if (scope.get("query_string") or scope.get("raw_path", path.encode()) != path.encode()
                or path not in {"/mcp", METADATA}):
            return await self.respond(send, 404)
        if path == METADATA:
            if method != "GET":
                return await self.respond(send, 405)
            return await self.app(scope, receive, send)
        # Bound public admission before RSA verification, not only valid owners.
        now = time.monotonic()
        self.credit = min(5.0, self.credit + (now - self.rate_updated) / 2)
        self.rate_updated = now
        if self.credit < 1 or self.inflight >= 4:
            return await self.respond(send, 429, extra=[(b"retry-after", b"2")])
        self.credit -= 1
        bearer = headers.get(b"authorization", b"")
        matched = re.fullmatch(rb"Bearer +([A-Za-z0-9_.-]{1,8192})", bearer, re.IGNORECASE)
        if not matched:
            access = None
        else:
            access = await self.verifier.verify_token(matched.group(1).decode("ascii"))
        if access is None:
            return await self.respond(send, 401, extra=[(b"www-authenticate",
                f'Bearer resource_metadata="{ORIGIN}{METADATA}"'.encode())])
        if "ynab:read" not in access.scopes:
            return await self.respond(send, 403, extra=[(b"www-authenticate",
                b'Bearer error="insufficient_scope", scope="ynab:read"')])
        # POST JSON and DELETE are sufficient for Streamable HTTP; no unsolicited SSE channel.
        if method not in {"POST", "DELETE"}:
            return await self.respond(send, 405, extra=[(b"allow", b"POST, DELETE")])
        if method == "DELETE" and headers.get(b"mcp-protocol-version") != PROTOCOL.encode():
            return await self.respond(send, 400)
        now = time.monotonic()
        for key, old in list(self.sessions.items()):
            if now - old.touched > 600 or old.dead:
                old.dead = True
                if old.client is not None:
                    await old.client.close()
                del self.sessions[key]
        sid_bytes = headers.get(b"mcp-session-id")
        sid = sid_bytes.decode("ascii", errors="replace") if sid_bytes else None
        write_scope = "ynab:write" in access.scopes
        # A refreshed token may retain a session only with identical privileges.
        # A downgraded token can never reuse a child that was started with writes.
        principal = (self.identity.issuer, access.subject, access.client_id, write_scope)
        session = self.sessions.get(sid) if sid else None
        if sid and (session is None or session.principal != principal):
            return await self.respond(send, 404)
        if session and session.connected and not session.client.is_connected():
            session.dead = True
            return await self.respond(send, 404)
        if self.inflight >= 4:
            return await self.respond(send, 429, extra=[(b"retry-after", b"2")])
        self.inflight += 1
        fresh = False
        context = None
        try:
            if session and session.connected:
                try:
                    async with asyncio.timeout(2):
                        await session.client.ping()
                except Exception:
                    session.dead = True
                    await session.client.close()
                    return await self.respond(send, 404)
            body = b""
            async with asyncio.timeout(5):
                if method == "POST":
                    if headers.get(b"content-type", b"").split(b";")[0] != b"application/json":
                        return await self.respond(send, 415)
                    if b"content-encoding" in headers:
                        return await self.respond(send, 415)
                    while True:
                        message = await receive()
                        if message["type"] != "http.request":
                            return
                        body += message.get("body", b"")
                        if len(body) > 262144:
                            return await self.respond(send, 413)
                        if not message.get("more_body"):
                            break
                    try:
                        rpc = json.loads(body)
                    except (ValueError, RecursionError):
                        return await self.respond(send, 400)
                    if not isinstance(rpc, dict) or rpc.get("jsonrpc") != "2.0":
                        return await self.respond(send, 400)
                    operation = rpc.get("method")
                    params = rpc.get("params", {})
                    if not isinstance(operation, str) or not isinstance(params, dict):
                        return await self.respond(send, 400)
                    if operation not in {"notifications/initialized", "notifications/cancelled"} and rpc.get("id") is None:
                        return await self.respond(send, 400)
                    if operation not in {"initialize", "notifications/initialized", "notifications/cancelled",
                                         "tools/list", "tools/call", "resources/list", "resources/templates/list",
                                         "resources/read", "prompts/list", "prompts/get", "ping"}:
                        return await self.respond(send, 403)
                    if operation == "initialize":
                        if session or params.get("protocolVersion") != PROTOCOL:
                            return await self.respond(send, 400)
                        if len(self.sessions) + self.pending >= 2:
                            return await self.respond(send, 429)
                        self.pending += 1
                        fresh = True
                        session = Session(principal, now, writes=self.allow_writes and write_scope)
                    elif session is None:
                        return await self.respond(send, 404)
                    elif headers.get(b"mcp-protocol-version") != PROTOCOL.encode():
                        return await self.respond(send, 400)
                    if operation == "tools/call":
                        if not isinstance(params.get("name"), str):
                            return await self.respond(send, 400)
                        name = params["name"]
                        allowed = READ_TOOLS | (WRITE_TOOLS if session.writes else set())
                        if name not in allowed:
                            return await self.respond(send, 403)
                        if name in {"ynab_tool_execute", "ynab_write_tool_execute", "preview_write_tool"}:
                            arguments = params.get("arguments", {})
                            if not isinstance(arguments, dict) or not isinstance(arguments.get("tool_name"), str):
                                return await self.respond(send, 400)
                            target = arguments["tool_name"]
                            targets = READ_TOOLS if name == "ynab_tool_execute" else WRITE_TOOLS - {"preview_write_tool", "ynab_write_tool_execute"}
                            if target not in targets or target.startswith("ynab_"):
                                return await self.respond(send, 403)
                    if operation in {"resources/read", "prompts/get"}:
                        value = params.get("uri" if operation == "resources/read" else "name")
                        if not isinstance(value, str):
                            return await self.respond(send, 400)
                        if value not in (RESOURCES if operation == "resources/read" else PROMPTS):
                            return await self.respond(send, 403)
                    rpc_id = rpc.get("id")
                    if rpc_id is not None:
                        if type(rpc_id) not in {str, int} or len(str(rpc_id)) > 128:
                            return await self.respond(send, 400)
                        unique = (type(rpc_id), rpc_id)
                        if unique in session.ids or len(session.ids) >= 512:
                            return await self.respond(send, 409)
                        session.ids.add(unique)
                elif session is None:
                    return await self.respond(send, 404)
            session.touched = now
            context = CURRENT_SESSION.set(session)
            messages = []
            size = 0
            async def capture(message):
                nonlocal size
                size += len(message.get("body", b""))
                if size > 2_097_152:
                    raise ValueError("Response limit")
                messages.append(message)
            consumed = False
            async def replay_body():
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()
            # Do not forward untrusted proxy identity, cookies or alternate auth.
            safe_scope = dict(scope, headers=[(k, v) for k, v in scope["headers"] if k.lower() not in {
                b"forwarded", b"x-forwarded-host", b"x-forwarded-proto", b"x-forwarded-for",
                b"x-forwarded-user", b"x-real-ip", b"cf-connecting-ip", b"x-api-key", b"cookie", b"authorization"}]
                + [(b"authorization", b"Bearer " + matched.group(1))])
            async with asyncio.timeout(min(30, max(0.01, access.expires_at - time.time()))):
                await self.app(safe_scope, replay_body, capture)
            start = next(message for message in messages if message["type"] == "http.response.start")
            if start["status"] >= 400:
                return await self.respond(send, start["status"])
            # Validate/redact the complete bounded JSON before sending headers.
            # ASGI body chunks are not independent JSON documents.
            response_body = b"".join(message.get("body", b"") for message in messages
                                     if message["type"] == "http.response.body")
            if response_body:
                payload = json.loads(response_body)
                if "error" in payload or payload.get("result", {}).get("isError"):
                    response_body = json.dumps({"jsonrpc": "2.0", "id": payload.get("id"),
                        "error": {"code": -32603, "message": "Request failed"}}).encode()
                elif method == "POST" and operation == "tools/list":
                    # Upstream normally hides write tools on read-only children;
                    # keep public discovery scoped even if that contract drifts.
                    allowed = READ_TOOLS | (WRITE_TOOLS if session.writes else set())
                    payload["result"]["tools"] = [tool for tool in payload["result"]["tools"] if tool.get("name") in allowed]
                    response_body = json.dumps(payload).encode()
            start["headers"] = [(k, v) for k, v in start["headers"]
                                if k.lower() not in {b"cache-control", b"content-length"}]
            start["headers"] += [(b"cache-control", b"no-store")]
            if fresh:
                native_sid = dict(start["headers"]).get(b"mcp-session-id")
                if native_sid:
                    self.sessions[native_sid.decode()] = session
            await send(start)
            await send({"type": "http.response.body", "body": response_body})
            if session.client is not None:
                session.connected = session.connected or session.client.is_connected()
            if method == "DELETE":
                session.dead = True
                self.sessions.pop(sid, None)
        except (Exception, asyncio.CancelledError):
            if session is not None:
                session.dead = True
                if session.client is not None:
                    await session.client.close()
            return await self.respond(send, 503)
        finally:
            if context is not None:
                CURRENT_SESSION.reset(context)
            self.inflight -= 1
            if fresh:
                self.pending -= 1
        return None


def from_config(secret_root=Path("/run/secrets")):
    logging.disable(logging.CRITICAL)
    if (os.environ.get("YNAB_ALLOW_WRITES", "0") not in {"0", "1"}
            or os.environ.get("YNAB_DISABLE_AGENT_CONFIG_FALLBACK", "1") != "1"
            or os.environ.get("YNAB_API_TOKEN") or os.environ.get("SENTRY_DSN")):
        raise ValueError("Unsafe gateway environment")
    files = [secret_root / name for name in ("gateway_identity.json", "oauth_public_key.pem", "ynab_api_token")]
    for path in files:
        metadata = path.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 65532
                or stat.S_IMODE(metadata.st_mode) != 0o400 or not 1 <= metadata.st_size <= 4096):
            raise ValueError("Invalid gateway configuration metadata")
    config = json.loads(files[0].read_text())
    if set(config) != {"issuer", "owner", "clients"}:
        raise ValueError("Invalid gateway identity configuration")
    if not isinstance(config["clients"], list):
        raise ValueError("Invalid gateway clients")
    identity = Identity(config["issuer"], config["owner"], frozenset(config["clients"]), files[1].read_text())
    allow_writes = os.environ.get("YNAB_ALLOW_WRITES", "0") == "1"
    if allow_writes:
        data = Path("/data").lstat()
        if (not stat.S_ISDIR(data.st_mode) or data.st_uid != 65532 or data.st_gid != 65532
                or stat.S_IMODE(data.st_mode) != 0o700):
            raise ValueError("Protected persistent journal directory required")
    return Gateway(identity, allow_writes=allow_writes)


if __name__ == "__main__":
    try:
        import uvicorn
        gateway = from_config()
        uvicorn.run(gateway, host="0.0.0.0", port=8000, proxy_headers=False,
                    access_log=False, log_config=None, limit_concurrency=8,
                    timeout_keep_alive=5, workers=1)
    except Exception:
        print("YNAB gateway prerequisite failed", file=__import__("sys").stderr)
        raise SystemExit(1) from None
