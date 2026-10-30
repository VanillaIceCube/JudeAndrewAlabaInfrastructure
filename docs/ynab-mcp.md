# 🧾 YNAB MCP gateway decision

Architecture and disposable evidence for [#57](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/57),
under [#56](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/56).
Reviewed 2026-10-28. **No production service or public endpoint is enabled.**

## 🧭 Decision and boundaries

**2026-10-29 #59 amendment:** reopen the conditional choice below in favor of
FastMCP 4.1.4's maintained stateful proxy/resource-server APIs, because no acceptable
Supergateway artifact is available. PR #65 supplies the hashed Python lock/scanner
prerequisite. The [inactive authenticated gateway](../services/ynab-gateway/README.md)
defines the replacement's exact OAuth resource-server/session/route contract and
its independent synthetic image acceptance. Public/provider/client activation
remains separately gated; known-advisory checks alone establish no lifecycle proof.
The original Supergateway experiment remains historical regression evidence;
its dependency findings are not waived. #59 authentication/session acceptance
must pass before #60 can supply an inactive route.

Select **FastMCP's maintained stateful Streamable HTTP-to-stdio proxy** for #59,
with one upstream child per MCP session and a single owner security domain per
gateway instance. Keep Oliver Ames's application unchanged and consume reviewed
upstream source with its lockfile. Do not fork, vendor, implement another protocol
engine, or connect YNAB to Notoli's users/OAuth database.

The original #57 Supergateway **4.2.1 selection is superseded and blocked for
production**: its locked runtime dependency graph has high/critical advisories.
Do not resolve this by silently running `npm audit fix`, relaxing pins or adding
local dependency overrides. Its seven-test experiment remains historical evidence
only; the replacement needs its own complete authentication/lifecycle acceptance.

**Historical #57 evidence only:** Supergateway's native API-key authentication
sufficed for that private transport experiment. It does not apply to the selected
FastMCP replacement. It lacks OAuth, expiry, scopes, client identity or
principal-to-session binding. Therefore it is **not the public authentication
boundary**. Public ingress remains blocked until #59 supplies reviewed OAuth
resource-server enforcement and the client acceptance described below. The
existing [optional MCP contract](optional-mcp.md) continues to apply.

## 🔎 Candidates and maintenance evidence

| Candidate examined | Evidence | Disposition |
| --- | --- | --- |
| Supergateway 4.2.1, MIT, `a78bd90804d3080e8268961949f22575b34826f0` | [Release](https://github.com/supercorp-ai/supergateway/releases/tag/v4.2.1), [session lifecycle](https://github.com/supercorp-ai/supergateway/blob/a78bd90804d3080e8268961949f22575b34826f0/src/gateways/statefulSessions.ts), [authentication](https://github.com/supercorp-ai/supergateway/blob/a78bd90804d3080e8268961949f22575b34826f0/src/lib/apiKey.ts). Released October 24 with Windows process-tree cleanup and empty-key configuration fixes; upstream reports cross-platform soak tests. | Original #57 selection, now superseded; seven local contract tests below pass. Dependency audit blocks the evaluated pin from production. |
| FastMCP 4.1.4, Apache-2.0, `26bf9080ae338d1467dca6471b15c6911f71c75c` | [Release](https://github.com/PrefectHQ/fastmcp/releases/tag/v4.1.4), [proxy provider and client factory](https://github.com/PrefectHQ/fastmcp/blob/26bf9080ae338d1467dca6471b15c6911f71c75c/fastmcp_slim/fastmcp/server/providers/proxy.py). Active broader Python framework with OAuth support. | Selected #59 replacement with a pinned Python graph; runtime acceptance is not included in this prerequisite. Adds another runtime/framework; complete identity/session/failure acceptance remains required. The original Supergateway experiment does not certify this proxy. |
| TBXark/mcp-proxy 1.1.0, MIT, `a0e6dfb620020a729338e8c993aaa45667211de4` | [Release](https://github.com/tbxark/mcp-proxy/releases/tag/v1.1.0), [downstream client lifecycle](https://github.com/tbxark/mcp-proxy/blob/a0e6dfb620020a729338e8c993aaa45667211de4/client.go), [HTTP/auth routing](https://github.com/tbxark/mcp-proxy/blob/a0e6dfb620020a729338e8c993aaa45667211de4/http.go). Maintained Go aggregation proxy. | Its aggregated downstream-client model is not evidence of one isolated stdio process per remote session. Extra isolation work and another runtime offer no demonstrated advantage here. Not runtime-tested. |
| Owned minimal SDK adapter | Would own authentication, streaming, cancellation, child cleanup, session isolation, errors and ongoing protocol updates. | Reject for now: larger security maintenance obligation than configuring a vetted transport. An unauthenticated proxy or per-request process is unacceptable. |

These are bounded source/release reviews, not independent security audits of
entire projects. No candidate is approved for public production by this document.

## 📌 Reproducible pins and supply chain

The experiment's [gateway pin](../experiments/ynab-mcp/pins.json) and the canonical
[runtime source pin](../services/ynab-mcp/upstream.json) record full commits and
SHA-256 hashes of both upstream npm lockfiles:

| Source | Evaluated version / full commit | Lock SHA-256 |
| --- | --- | --- |
| Oliver Ames YNAB MCP | 6.1.0 / `076aa5836658f8332058fa2bd58500aa14326dc9` | `2619d837be950b52b4ee2a729c9cefaec504499962283c895f2fb6115f0876a6` |
| Supergateway | 4.2.1 / `a78bd90804d3080e8268961949f22575b34826f0` | `f600671d77f6ac96279ee418381c40c8b2a515376972c15c0ebcd372bfcab943` |

`run.py` checks the commit, clean tracked source and lock hash; installs with
`npm ci --ignore-scripts`; and invokes the pinned TypeScript compiler directly.
Lock hashes use the original Git blob's LF bytes; checkout explicitly disables
Windows CRLF conversion. It never selects `latest`, runs `npx -y`, modifies
upstream source or uses a
published npm tarball as if source equivalence had been established. npm checks
the lockfile's package integrity. Node 24 matches existing Infrastructure CI.

On the review date, `npm audit --omit=dev --json` reported **12 affected gateway
packages: 1 critical, 6 high and 5 moderate**; Oliver's source reported **2
moderate packages**. Counts describe affected packages, not unique advisories.
Gateway findings include
[proxy-addr trust spoofing](https://github.com/advisories/GHSA-jqcg-44mw-7w3h),
[MCP shared HTTP transport isolation](https://github.com/advisories/GHSA-jm63-cq47-j5jp),
[MCP validation memory exhaustion](https://github.com/advisories/GHSA-46jr-4wx8-v453),
and [body-parser decompression denial of service](https://github.com/advisories/GHSA-27r3-jxmh-p828).
Some concern unused OAuth-client/static-file paths; this is not a blanket
reachability waiver. Oliver's lock resolves SDK 1.32.1, whereas the evaluated
gateway pins SDK 1.30.0 and also carries 2.0.0 SDK packages. Do not equate their
security status merely because both use MCP.

#58's [isolated runtime](../services/ynab-mcp/README.md) verifies package/source
parity, fails high/critical npm audits and runs network-disabled container tests.
It is not an approved production image. Before promotion, retain fresh
advisory/license/malware evidence, assess every remaining
finding, verify source/package provenance if choosing a registry artifact, and
build an immutable image with pinned base digest and recorded output digest.
The upstream Dockerfile's mutable `node:22-alpine` is not a production image pin.
No image was built, pushed or selected here. #61 owns continuing dependency
scanning; existing repository gates remain intact.

## 🧪 Disposable protocol and preview proof

On a disposable workstation/CI runner with Git, Python and Node 24/npm:

```sh
python experiments/ynab-mcp/run.py
```

The existing `validate.yml` automation step runs this same command with Node 24
and a four-minute process limit; failures block the existing Required CI gate.
Revalidate every harness/pin change and each proposed upstream upgrade. This
protocol fixture does not replace #61's production supply-chain/release gates.

Sources, packages, fixture HOME and working files are temporary and removed on
exit. Package downloads require internet. This is a local-process experiment,
not a hostile-code sandbox: use a disposable runner without credentials. The
gateway listens on an ephemeral **127.0.0.1** port only; nothing is deployed.
The runner passes a small environment allowlist and a temporary npm user config,
excluding operator YNAB/OpenAI/cloud credentials and `NODE_OPTIONS`.

The [test child](../experiments/ynab-mcp/fake-child.mjs) imports Oliver's unchanged
`createYnabServer` and real SDK stdio transport. Its injected fake API implements
synthetic plan/payee reads and an in-memory payee mutation. There is no real YNAB
token, HTTP request to YNAB, budget, journal file, or financial mutation. A global
fetch trap rejects accidental real network calls. The synthetic write test uses
the factory's explicit test option; `YNAB_ALLOW_WRITES` stays `0`. Fixture-only
status/clock/cancellation tools must never be shipped in a production image.

Seven executable tests establish:

- Missing/wrong bearer credentials reject POST/GET/DELETE with 401 before JSON
  parsing or session access, even with spoofed forwarding headers. Authenticated
  malformed JSON gives 400; unknown sessions give 404; responses carry no-store.
- Real `initialize`, initialized notification, `tools/list` and read-only
  `list_budgets` work; write tools are hidden and direct write calls fail.
- New TCP requests and an SSE disconnect retain the same upstream PID/session;
  another initialize creates a different child. DELETE invalidates the old ID.
- A real upstream `preview_write_tool` token performs zero fake writes until
  `confirmed:true`; `confirmed:false` fails. One approved execution succeeds
  and token replay fails with the fake mutation count remaining one.
- Another session cannot use that preview. Changing the exact proposed payload
  fails and consumes the stale token. Neither child performs a fake write.
- Advancing the injected clock beyond five minutes expires a token. Replacing
  the child invalidates its old previews; they cannot migrate to a new session.
- A long request permits concurrent status calls, forwards MCP cancellation
  without replacing its child, and an idle session expires with a 404. Separate
  owner instances reject each other's credentials/session IDs.

This proves a **persistent logical MCP session**, not a persistent TCP socket.
It does not prove real-client behavior, full event replay/resumption, arbitrary
protocol-version compatibility, proxy behavior, OAuth, or production capacity.
Tests negotiate `2025-11-25`; newer stateless protocol paths are not accepted by
this design until the same preview/isolation contract is re-established. A
client that initializes afresh for each tool call cannot complete local previews.

## 🔐 Authentication, identities and exact routes

The following paragraph/table record **historical Supergateway-only evaluation**;
they are not FastMCP configuration instructions. #59 must deliver the replacement
authentication contract and its own executable acceptance evidence.

For that private transport evaluation, configure exactly one random owner key per
instance through a protected file; reject absent/empty configuration at startup.
Use `Authorization: Bearer`, never query credentials. Supergateway also accepts
`X-API-Key`; a future public edge must strip it so it cannot bypass OAuth.
Never put unrelated identities or clients behind Supergateway's multi-key list:
keys authorize the entire instance, and session IDs are not bound to a key.
Restart on key rotation/revocation so all sessions and previews are invalidated.
Static keys have no native expiry, scopes, replay prevention or consent screen.

| Route | Evaluated transport behavior | Future edge requirement |
| --- | --- | --- |
| Exact `/mcp`, POST/GET/DELETE | Stateful Streamable HTTP; bearer required; authenticated initialization creates a child | Forward only after resource authorization; exact route, original URI, HTTP/1.1, empty Connection, buffering off, bounded idle timeout and no-store |
| `/.well-known/oauth-protected-resource/mcp` | **Not implemented** by Supergateway | #59 must implement this exact public metadata path before public ingress; challenge must advertise it with resource `https://ynab.judeandrewalaba.com/mcp` |
| Authorization-server discovery, authorize/token/revoke and consent | **Not implemented** by Supergateway | Use a separately reviewed maintained OAuth 2.1 provider with documented exact issuer/endpoints. Serve on the selected authorization host; do not invent or copy Notoli `/auth/mcp/*` paths |
| `/mcp/` | Express also matches the trailing slash internally | Future edge must expose only exact `/mcp`; reject this alias without redirect/rewrite |
| Health/admin/debug, `/sse`, `/message`, WebSocket | Not enabled in this experiment | Never forward implicitly or use an SPA 200 as discovery; keep future liveness/readiness private and redacted |

For the public target, #59 must validate tokens on **every** MCP method before
dispatch: fixed issuer/JWKS, audience/resource, expiry, `ynab:read` scope, allowed
owner subject and registered client, plus session ownership by subject/client.
Return resource-metadata 401 challenges, 403 for insufficient authorization,
and 404 for another owner's session. Never relay an OAuth access token to YNAB;
use the private server-held YNAB token, never a caller credential, for the stdio
child. The selected colocated proxy needs no HTTP bridge credential. Isolate
processes/caches/journals per owner; a future second owner requires a new design
review. Do not trust any `X-Forwarded-User`, user-supplied Host, or session ID as
identity. Strip alternate bridge-key/forwarded identity headers; they cannot bypass OAuth.

Use authorization-code + S256 PKCE, exact preregistered HTTPS callbacks, resource
binding, explicit owner consent, revocation and short-lived access tokens; no
password/implicit grants or open dynamic registration. This follows #28's
registered-client policy. #59 implements the protected resource with a pinned
maintained verifier and static issuer public key, not an authorization server.
Provider selection/provisioning (including a reviewed artifact pin if self-hosted),
owner consent/client configuration and real-client acceptance remain **#62
operator gates**; source acceptance does not waive them.
Do not publish metadata or ingress forwarding for nonexistent endpoints.

Codex supports local stdio and remote HTTP with bearer/OAuth configuration;
private bearer transport can therefore be evaluated with Codex. ChatGPT remote
plugin authentication expects the [MCP OAuth contract](https://developers.openai.com/plugins/build/auth),
protected-resource metadata, S256 and a supported client registration flow.
See [OpenAI's MCP connection guide](https://developers.openai.com/codex/mcp).
This experiment is not ChatGPT acceptance, and an HTTPS 200 is not proof of
account/plan/workspace availability. #62 must test the actual intended client,
its permissions, registration/callback behavior and session continuity. If a
client cannot retain local preview sessions, keep it read-only; future writes
require another approved design. No client is connected to a real budget here.

## 🛡️ Threat model and required controls

| Threat | Control / remaining validation |
| --- | --- |
| Bearer theft/replay | TLS, protected secret files, redacted logs, short expiry/revocation at OAuth boundary; keys remain replayable if stolen. A unique JSON-RPC ID is not replay protection. Never retry an ambiguous write; previews are single-use and not human consent. |
| Cross-session/client access | One child per session; one owner domain per instance; public subject/client-to-session enforcement before forwarding. Native multi-key authentication alone is insufficient. |
| Spoofed headers, DNS rebinding, browser CSRF | Fixed host at Nginx, exact reviewed proxy peer, overwritten forwarding headers, explicit Host/Origin allowlist before tool access. Disabled CORS is not an Origin check. These public-edge tests belong to #59/#60. |
| SSRF and confused deputy | Fixed executable/arguments and API origin; no caller-supplied process, upstream URL, token, redirect target or forwarded identity. Egress only to necessary DNS/YNAB destinations; narrowly pin OAuth issuer/JWKS fetch policy. |
| Untrusted transaction memos/payees | Treat all financial strings as data. Never translate content into new instructions, consent or write permission. Runtime writes remain disabled regardless of model requests. |
| Resource exhaustion | Proposed initial limits: two owner sessions, four in-flight requests per owner, 256 KiB ingress bodies, 30 requests/minute with burst five, ten-minute idle session TTL and 120-second edge idle timeout. #59/#61 must enforce/test these and choose measured CPU/RAM/PID limits before deployment. Native 4 MiB parsing/idle timeout alone is insufficient. |
| Logs and errors | No request/response bodies, query strings, Authorization/session/preview tokens, OAuth codes, raw child stderr or budget records. Gateway `logLevel none` until redaction is proven; bounded status/error-category metrics and private 10 MiB × 3 container logs. No Sentry DSN. |
| Credentials/journal at rest | Separate YNAB token and OAuth/bridge secrets; 0700 directories, 0600 files, runtime-compatible ownership, read-only secret mounts. `YNAB_DISABLE_AGENT_CONFIG_FALLBACK=1`, `YNAB_ALLOW_WRITES=0`. No agent HOME mounts. Future write/undo/operation journals need an owner-private volume, encrypted backups, retention and explicit matched recovery. |
| Child failure/reconnect/upgrade | Session closes when its child dies; fail old ID with 404, require fresh initialize and new preview. Never spawn per request or automatically resume a financial write. Health 200 alone cannot establish credentials, API health or tool readiness. |

## 📦 Hosting and ordered handoff

Reuse [architecture v2](architecture-v2.md), the [release standard](app-release-standard.md),
and [gateway release/recovery](gateway-releases.md). Do not alter `app-release/v1`
or app-vendored copies for this decision. The shared transaction is currently
designed for Django/SQLite apps; #61 must assess a configuration-only service
profile rather than copying the engine or inventing fake migrations/databases.

1. **#57, this PR:** architecture, source/lock pins and disposable proof. Existing
   Compose, Nginx, app networks, certificates, credentials and deployment workflows
   unchanged. The existing validation workflow also runs the bounded experiment.
2. **#58:** resolve advisory/provenance gates, then isolated non-root immutable
   runtime; no host ports/Docker socket, minimal read-only filesystem/capabilities,
   measured resource limits, independent secrets and deliberate journal policy.
3. **#59, after #57/#58:** configure stateful gateway and maintained OAuth boundary;
   enforce identity, scope/session, Origin/Host, limits, safe readiness/logs and
   all negative security tests. Remains read-only. No public ingress yet.
4. **#60, after authenticated acceptance:** separate YNAB-only external route
   network, operator-owned membership, exact vhost and implemented metadata;
   preserve Notoli's exact `.2` proxy trust and every existing network/vhost.
   DNS/TLS/Cloudflare/firewall changes require separate authorization. Reuse
   existing streaming/Docker DNS/header/log directives, not a second ingress.
5. **#61:** build ongoing protocol/security/upgrade tests and independent YNAB
   release/rollback with existing maintenance locks, immutable records and
   explicit prior-image/config recovery. Coordinate monitoring/backups with #24
   and gateway acceptance with #14; do not duplicate their implementations.
   Develop this alongside #58/#59, but pass it before any #62 activation.
6. **#62:** exact operator plan, resource capacity, private recovery and real
   client read-only acceptance after separate owner approval. No financial
   writes, credential deployment or public service activation from source merge.

Upgrades invalidate in-memory sessions/previews and require new initialization;
announce this rather than claiming seamless resumption. Retain the previous
verified immutable image/configuration and private recovery state. Roll back the
YNAB app independently under its app/shared maintenance locks. Removing a route
is a separate gateway release; never `down --remove-orphans`, prune globally,
recreate shared networks or rerun initial host cutover. Writes/journal restoration
and any resulting data loss require an explicit future operator decision.

## 🚧 Owner follow-up

Before #59/#62, confirm the actual client surfaces and owner identities to
support, approve the OAuth provider/client-registration choice, and review the
patched upstream dependency evidence. Only after those gates should the owner
approve an exact read-only activation and private credential-provisioning plan.
No credentials are needed for #57. Sanitized progress belongs in #56; private
host/account/capacity and provider-request details belong in KnowledgeVault.

## 🚀 First activation

The [ordered operator procedure](ynab-operations.md) combines the reviewed issuer,
YNAB and gateway release guides without a new deployment framework. Use actual
ChatGPT and Codex callback registration, consent and read-only tool acceptance.
Budget selection is client/tool input; the upstream does not provide a supported
`YNAB_BUDGET_ID` environment selector. Keep #62 open for observed live evidence.
