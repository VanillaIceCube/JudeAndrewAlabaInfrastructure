# 🔐 Inactive YNAB authenticated gateway

This #59 candidate wraps Oliver's unchanged stdio application with FastMCP's
maintained stateful HTTP proxy and OAuth resource-server APIs. The manual Compose
profile is inactive, has no network or published ports and never restarts itself.
No issuer, client, credential or production deployment is provisioned. #60/#61/#62
and separately approved operations remain required before activation.

## 📌 Maintained fallback and pins

The conditional Supergateway 4.2.1 choice in #57 remains blocked by high/critical
runtime advisories. Reopen that choice in favor of **FastMCP 4.1.4**, using
`fastmcp-slim[server,client]==4.1.4`; its maintained stateful proxy and resource-server
authentication APIs avoid owning another MCP protocol engine. The full upstream
source commit is `26bf9080ae338d1467dca6471b15c6911f71c75c` (Apache-2.0).
Oliver's unchanged application and canonical source pins remain under
[`../ynab-mcp`](../ynab-mcp/README.md). No fork or dependency overrides.

`requirements.txt` pins the complete Linux/Python 3.12 graph with SHA-256 artifact
hashes. Preserve its two-line canonical-input/scanner header on regeneration.
Generate updates in a disposable Linux container using Python 3.12,
`pip==26.2` and `pip-tools==7.6.2`, with this single input line in a temporary
`requirements.in` (do not add another unscanned manifest):

```text
fastmcp-slim[server,client]==4.1.4
```

```sh
pip-compile --generate-hashes --resolver=backtracking --strip-extras \
  --no-emit-index-url --no-emit-trusted-host \
  --output-file=requirements.txt requirements.in
python scripts/check_gateway_dependencies.py
```

Install only using `pip install --require-hashes -r requirements.txt` in a disposable
environment. Hashes identify downloaded bytes; they do not authenticate the
publisher or prove absence of malicious code. Review new dependencies, artifacts,
licenses and provenance on every update. Build tools are not runtime dependencies.

## 🛡️ Existing CI boundary

The existing dependency-scope gate now supports this **exact** lock path. All
other package manifests continue to fail closed until scanner support is reviewed.
It validates exact versions/hashes without installing packages, queries the
[OSV batch API](https://google.github.io/osv.dev/post-v1-querybatch/) for all pins,
and checks each hash and yank status against the
[PyPI release JSON API](https://docs.pypi.org/api/json/).
Known advisories at any severity, catalogued malware, incomplete/unavailable
metadata, pagination and redirects fail the gate. Only package names, versions
and public hashes are sent; no provider account APIs or credentials are involved.

These checks do not detect unknown malware or scan container layers, and do not
grant license/provenance approval. #61 retains full-image and release acceptance.
The initial 2026-10-29 scan of 61 pinned packages found no known OSV advisories;
repeat the live check rather than treating that result as permanent.

## 🔐 Resource server and authorization-provider contract

Production configuration has three separately mounted, regular files, owned by
uid 65532 with mode 0400, in an operator/root-owned 0700 directory. Reuse the
runtime's [secret metadata preflight](../ynab-mcp/README.md); never mount a HOME,
Docker socket, shared application secret directory or inline token.
Gateway startup checks all three files' regular-file type, uid, mode and bounded
size before constructing the server or starting a child. The existing Node policy
also validates the token before loading unchanged upstream code; Python never
reads the token contents. Readiness still detects later missing/dead children or
unavailable token mounts without claiming API validity.

- `ynab_api_token`: Oliver's token, validated by the unchanged #58 policy, with
  `YNAB_ALLOW_WRITES=0` and fallback disabled regardless of client requests.
- `gateway_identity.json`: exactly `issuer` (HTTPS authorization-server issuer),
  `owner` (one fixed subject), and `clients` (one to eight explicit registered client
  IDs). These private identity details do not belong in Git or public issue notes.
- `oauth_public_key.pem`: the issuer's RSA public key, at least 2048 bits. Private
  keys, remote JWKS URLs, opaque tokens and shared HMAC keys are not accepted.

The maintained pinned `JWTVerifier` verifies RS256 signatures/issuer/audience.
The owner policy additionally requires `typ: at+jwt`, integer `iat`/`exp`, at most
15 minutes of token lifetime, no future `nbf`, exact resource audience (a string),
the configured subject/client and consistent `azp` if present. Every MCP method
requires a bearer and `ynab:read`; no cookies, query credentials, API keys or
forwarded user identity. A refreshed token for the same principal can retain a
session. Another client/subject/issuer cannot use it. Session IDs are not credentials.

This is a **protected resource**, not an authorization server. Select/provision a
separately reviewed maintained authorization provider before #62 activation. It
must implement authorization-code/S256 PKCE, exact preregistered HTTPS callbacks,
explicit owner consent, the exact resource audience, refresh-token rotation and
revocation; no password/implicit grant or open dynamic registration. It must issue
the claim contract above. Keep its database/grants separate from Notoli. Owner
approval of that provider/client configuration and actual client acceptance are
outstanding operator steps; a synthetic issuer does not establish them.

No runtime JWKS fetching avoids another SSRF/egress path. Rotate the mounted
public key through a reviewed release and recreate this gateway: this invalidates
all sessions/previews. Token revocation at the issuer does not revoke already
issued offline JWTs immediately; exposure lasts up to 15 minutes. Emergency
owner/client disablement requires gateway configuration/restart. Do not claim
instant revocation or protection if a valid bearer is stolen.

| Exact path | Contract |
| --- | --- |
| `/mcp` POST | Auth before JSON parsing; protocol `2025-11-25`, initialized stateful session, JSON responses for initialize/list/read-only calls and notifications |
| `/mcp` DELETE | Authenticated, principal-bound session termination; same protocol header required |
| `/mcp` GET | Authenticated 405; this server does not offer an unsolicited SSE channel or event replay/resumption |
| `/.well-known/oauth-protected-resource/mcp` GET | Maintained RFC 9728 metadata; resource is `https://ynab.judeandrewalaba.com/mcp`, authorization server comes from the reviewed fixed configuration |
| `/health/live`, `/health/ready` GET | Loopback peer only; never route publicly. Readiness initializes a separate bounded stdio child and checks tool/auth status without calling YNAB; missing child/token returns 503. Ten-second cache; not proof of YNAB availability. |

No `/mcp/` alias, encoded path, query, wildcard discovery, OAuth authorize/token
route, debug/admin, SSE, WebSocket or frontend route is exposed. Fixed public Host
and exact Origin (if supplied) are checked before forwarding; proxy headers never
create identity. The fixed Origin check precedes maintained middleware; public metadata may carry discovery CORS headers. The future ingress must preserve the
exact routes, canonical Host and no-store/error redaction without exposing health.

## 🧵 Session and safety limits

Each logical remote session gets its own **transport object**, then uses
`StatefulProxyClient.new_stateful` to cache one child on the maintained SDK
connection. FastMCP client cloning alone shares a transport and is insufficient.
No child per request, shared connected backend or custom protocol engine. A
read-only ping verifies an established child before dispatch; child failure
invalidates its old ID with 404 rather than reconnecting silently. DELETE, idle
expiry and process restart discard previews. No automatic request retries.

The maintained SDK handles MCP negotiation/dispatch/cancellation and its native
principal binding; the policy also enforces owner/client session ownership. Newer
stateless protocols remain blocked until equivalent lifecycle/preview proof.
JSON responses are supported Streamable HTTP; live SSE/event resumption is not
claimed. Clients that require a different protocol/authorization profile must
remain blocked pending review.

Limits per owner process: two active sessions, four in-flight requests, 256 KiB
request bodies, 16 KiB total request headers, 30 MCP admission attempts/minute
with burst five (including invalid/anonymous attempts, before signature checking),
ten-minute idle sessions, 512 unique RPC IDs/session, five-second body read and
30-second execution bound capped by token expiry. Duplicate RPC IDs receive 409;
this prevents repeated logical calls, **not stolen-bearer replay**. Output is
bounded to 2 MiB. Pending initializations count toward the session quota. The
inactive profile uses 512 MiB, half a CPU and 64 PIDs; live host capacity remains
a separate acceptance check. It has a 32 MiB temporary filesystem and no journal
volume because writes/undo/operation executors are not exposed.

Only the explicit read-tool allowlist in `gateway.py` is advertised/accepted.
Generic executors, credential diagnostics/configuration and all write/preview/
undo/admin tools stay hidden and blocked even if an upstream change adds them.
Maintained resource/template/prompt discovery returns empty lists; resource reads
and prompt execution are denied. This matches the frontend's discovery capabilities
without exposing another data or execution path.
Financial strings remain data, never authorization or instructions. Future writes
require a separate design; the fixture-only factory option cannot enable them in
this image. No Sentry, request/response logging, raw child stderr, sensitive
metrics or token/error-body logging. Errors are generic and authenticated
responses are no-store; logging is disabled before production startup.

## 🧪 Build, preflight and disposable acceptance

```sh
python services/ynab-gateway/run_tests.py
python services/ynab-gateway/build.py --tag local-ynab-gateway:review --record /private/new-record.json
python services/ynab-gateway/validate.py --image ghcr.io/OWNER/ynab-gateway@sha256:DIGEST \
  --token-file /private/ynab_api_token --identity-file /private/gateway_identity.json \
  --public-key-file /private/oauth_public_key.pem
```

These are candidate commands; placeholders are deliberately not usable production
configuration. Build requires Docker/Git/internet, reuses #58's source/tag/lock/
package parity verification, verifies `manifest.json`, runs a fresh high/critical
upstream npm audit and installs the hashed Python graph as wheels only. Pinned
Node 24 and Python 3.12 Debian bookworm images share the C runtime; no fork or
vendored source. The final image removes Python installers/build tools and
checks the copied Node binary with `ldd` (no missing libraries) and `node --version`.
The Python base supplies glibc/libm/libdl/libpthread; libstdc++/libgcc are deliberately
copied from the pinned Node image. It contains no fixture server or secrets.
Local image ID/record is explicitly
unpublished and unapproved; a registry manifest digest and full-image/license/
provenance review still belong to #61. The gateway runs as uid/gid 65532.

The separate existing validation-workflow job builds this exact image, mounts
test fixtures read-only, runs with no network/capabilities and read-only root, then
removes only its uniquely labeled container/tag. The script directory cannot
shadow image source (`python -P`); tests assert they import `/gateway/gateway.py`.
The outer seven-minute timeout has exact-run cleanup on EXIT, including failures.
An additional network-disabled container launches the exact production ENTRYPOINT
with synthetic private files in a uniquely labeled volume, then verifies loopback
readiness, actual Node policy/upstream initialization/listing, anonymous rejection
and write denial. No financial API call is made. Its generated JWT stays in memory,
the signing key is never mounted, and exact-run cleanup removes the container/volume.
Its result/log is included in Required CI/Lint Eastwood evidence. No credentials
or actual financial/API requests are used.

Tests cover successful initialize/discovery/read-only invocation, negative token/
scope/identity/route/Host/Origin cases, safe errors/logs, quotas, expired tokens in
flight, stable distinct children, child death, cancellation, readiness and private
configuration. Test-only mounted factory options prove separate confirmation,
same-child previews, cross-session rejection, single use, payload change and
five-minute expiry using synthetic data. The historical Supergateway harness
does not substitute for these tests.

Read-only source/build/preflight never starts a production service. The default
Compose `network_mode: none` is deliberate; #60 must separately supply reviewed
route/egress source, and #61/#62 must supply release/recovery/client acceptance.
Rotate secrets with fresh protected files and recreate the selected gateway under
its app lock; bind mounts retain old file inodes. Preserve prior matched image,
configuration and private evidence for explicit rollback. No shared ingress,
network, application or database mutation belongs to a YNAB-only rollback.
