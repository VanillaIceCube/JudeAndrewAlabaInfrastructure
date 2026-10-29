# 🌐 Inactive YNAB routing and egress

Source plan for #60, after the authenticated #59 gateway. No route, DNS record,
network, certificate, firewall or Cloudflare setting is activated by this PR.
Existing `compose.yml`, application network objects and Notoli's exact proxy
trust remain unchanged. #61 release/security acceptance and #62's separately
approved operator plan are required before use.

## 🧭 Independent profiles

The base ingress loads only `nginx/vhosts`. The explicit `compose.ynab.yml`
overlay instead mounts `nginx/optional/ynab`, whose first file includes the
unchanged existing vhosts from a separate read-only mount. Their bytes and
default-server order are preserved without duplicate configurations. The new
vhost is last. Unknown hosts retain existing routing and cannot select YNAB.
Do not introduce a global unknown-host rejection as part of this feature.

The profile forwards only raw, exact `/mcp` and
`/.well-known/oauth-protected-resource/mcp`; aliases, encoded spellings, queries,
health/admin/debug, wildcard discovery and Notoli OAuth paths are rejected.
The OAuth authorization server remains external: there are no authorize/token/
callback endpoints on this backend. Host/forwarding rules come from existing
shared snippets; alternate API-key/user/cookie headers are stripped. The shared
Streamable HTTP transport include preserves existing Notoli behavior and provides
HTTP/1.1, empty Connection, response buffering off and a 120-second idle timeout.
YNAB additionally disables request buffering, limits bodies to 256 KiB and bounds
body/connect/send time. Authenticated application execution still has #59's
shorter deadline. Missing backends do not block Nginx startup or companion apps;
variable Docker DNS refreshes after recreation without an ingress reload.

All YNAB responses, including errors, are no-store. YNAB request logging is off
and raw Nginx error logging remains disabled; private paths, queries, tokens and
bodies do not enter new logs. Existing app logging policy is preserved. Status
and alert integration belong to #24/#61, with no financial data in labels/logs.

`compose.ynab-disabled.yml` is a separate, explicit disable/recovery profile. Its
hostname tombstone returns 410 rather than falling through to Notoli's default
vhost. It preserves existing routes and does not delete any network or stop an
application. Use base + **one** selected overlay, never stack enabled/disabled
profiles. Removing the new route and rolling back the YNAB app are separate
component operations under the existing maintenance lock.

## 🔒 Candidate network registry

These are proposed **new** operator-owned objects. Check current Docker/VPC/
host routes and IPAM for overlap before approving these exact addresses. If
overlap exists, revise/review all source contracts together; do not silently
renumber an existing application or repair networks during an app release.
Compose references all three as external and creates none.

| New object | Proposed IPAM | Required members |
| --- | --- | --- |
| `ynab_mcp_private`, internal bridge | `172.30.89.0/29`, gateway `.1` | Shared ingress `.2`; YNAB gateway `.3`, alias `ynab-mcp-gateway` |
| `ynab_mcp_egress_private`, internal bridge | `172.30.90.0/29`, gateway `.1` | YNAB gateway `.3`; CONNECT proxy `.2`, alias `ynab-egress` |
| `ynab_mcp_egress_public`, bridge | `172.30.91.0/29`, gateway `.1` | CONNECT proxy `.2` only |

YNAB joins no Notoli/MacroMapper network. Shared ingress joins only the new route
network in addition to its existing three attachments; its Notoli `.2` address
and exact trust are unchanged. The app has only internal networks, no host ports
and no direct internet path. The CONNECT proxy has no route-network membership
or published port. Docker/root administrators remain privileged; these conventions
are not adversarial isolation from the host operator.

The initial `services/ynab-gateway/compose.yml` remains network-disabled. Only its
separately approved `network.compose.yml` overlay replaces that setting. Before
activation, verify `Internal`, bridge driver, IPv6/IPAM, gateway, exact membership
and container IDs privately. Record network IDs for release/recovery preflight.
Provider firewall/routing and host capacity remain owner/operator acceptance,
not conclusions drawn from Compose config or a droplet's advertised size.

## 🔌 Fixed outbound path

The [egress recipe](../services/ynab-egress/README.md) pins a scan-compatible
Canonical Squid 6.13 amd64 base and two hash/version-pinned Ubuntu security
packages. It supersedes the original beta digest's HIGH findings while preserving
native package inventory. The inactive overlay requires a separately built,
reviewed immutable `YNAB_EGRESS_REPOSITORY`/`YNAB_EGRESS_SHA256` artifact, alongside
the gateway image pair; no mutable publisher channel is a deployment reference.
Review GPL notices, provenance, remaining findings and both exact full-image scans
in #61 before any promotion.

The non-root proxy runs uid/gid13 with read-only root, dropped capabilities, no
privilege escalation, no restart or logs/cache, 128 MiB, quarter CPU and 32 PIDs.
It permits only CONNECT to exact `api.ynab.com:443` and rejects common private,
loopback, link-local and reserved destinations. Other names, ports, plaintext
requests and IP literals are denied. There is no TLS interception or token at
the proxy; Node validates the API's normal certificate end to end. The proxy is
not a financial-write firewall: #59 and the unchanged runtime independently keep
writes disabled. DNS/host administrator compromise is outside this app boundary.
Review the [IANA special-purpose IPv6 registry](https://www.iana.org/assignments/iana-ipv6-special-registry/iana-ipv6-special-registry.xhtml)
alongside artifact updates; the deny list includes both IPv4 documentation ranges
and IPv6 `2001:db8::/32`/`3fff::/20`, plus local-use translation/SID ranges. New
network contracts require IPv6 disabled; the ACL remains an additional safeguard.

Node 24's [documented environment-proxy flag](https://github.com/nodejs/node/blob/v24.15.0/doc/api/cli.md#--use-env-proxy)
is enabled in the fixed child command; HTTP/HTTPS proxy authorities are exactly
`http://ynab-egress:3128`, with empty `NO_PROXY`. They cannot come from a caller or
an inherited workstation environment. No arbitrary URL, executable, issuer-key
fetch or direct fallback is configured. The proxy does not expose cache-manager
access. Keep the normal TLS trust store; the extra CA/private-address exception
used by the disposable test is never production configuration.

## ☁️ DNS, TLS and Cloudflare plan — no applied changes

Before approving a hostname change, privately inventory exact and wildcard DNS,
effective resolution, edge/origin certificate coverage/expiry, zone settings,
rule precedence, challenge/cache rules, origin restrictions and relevant plan
capabilities. An earlier read-only inventory found no exact YNAB record; that
does **not** establish absence of wildcard routing or prove certificate readiness.
Keep addresses, account/zone IDs and recovery exports in KnowledgeVault.

The separately approved plan must name the exact DNS target/type/proxy status,
prior value/TTL and reversal. Prefer the existing proxied ingress origin only
after its capability is verified. Do not create an additional droplet, expose
backend ports, relocate a certificate or copy application credentials. Validate
the proposed hostname's existing certificate/SAN and key access without exposing
key material. Preserve existing application certificate mounts/permissions.

Require [Full (strict)](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/):
the origin certificate must be current, trusted by a public CA/Origin CA and
match the hostname. Verify both public TLS and the approved origin path with
certificate validation; disposable self-signed tests do not prove either.

For exact host `ynab.judeandrewalaba.com`, approve an explicit
[cache-bypass rule](https://developers.cloudflare.com/cache/how-to/cache-rules/settings/)
for MCP/metadata and verify effective precedence, no-store and no cached auth
responses. Challenge-free API access is required for non-browser clients. Review
actual matching WAF/bot rules; use a narrowly scoped
[Skip exception](https://developers.cloudflare.com/waf/custom-rules/skip/)
only if a proven false positive requires it. Select only the necessary rule/
feature, host, exact paths and methods; keep unrelated protections and rate
limits. Do not disable zone-wide security, trust a bearer-shaped header as proof
of authentication, log matched payloads or add an interactive Access/challenge
page in front of MCP. The app still authenticates every MCP method.

No account API or DigitalOcean call is needed to prepare this source. Public
Cloudflare documentation reads/searches and their purposes/results were logged
privately. Any later provider request must likewise be logged **before** execution
and completed with result/mutation evidence. All changes require separate owner
authorization; record sanitized changes and outstanding actions in #56.

## 🧪 Disposable proof and release handoff

```sh
python -m unittest discover -s tests -p 'test_*ingress.py' -v
python services/ynab-gateway/run_tests.py
```

The first command reuses the existing ingress fixture helpers and tests all base
routes plus the inactive overlay: challenge/metadata, exact URI rejection,
no-store, header stripping, real incremental response delivery, missing/recreated
backend with a changed IP, unchanged companion/network identities and 410 disable
rollback. It never reads production certificates or runs cutover commands.

The gateway image runner also tests the real unchanged stdio application over a
synthetic TLS API and maintained CONNECT proxy, on two internal fixture networks.
Only the proxy joins both, and a direct client-to-API connection must fail.
The production ACL first denies the private resolved target; a temporary
test copy then permits only that exact fixture IP. The original ACL is verified
unchanged. Tests obtain the actual image's child command/environment, add only a
fixture CA, and verify a synthetic read. No live API request or financial write.
Unique labels and outer EXIT cleanup remove only that run's containers/networks/
volume/tag. Root discovery skips this image-dependent case; the dedicated gateway
CI job executes it and fails if it does not pass.

Profiles must pass #61's supported bundle/preflight/release interface before use;
the current default gateway transaction must not be bypassed with ad-hoc Compose
commands. #62 records the exact approved sequence and recovery. Main-source
merges supply neither live network creation nor public activation authorization.
The default transport archives only the existing base mount trees, excluding the
inactive optional directories so its strict extractor continues to accept the
normal payload. A regression extracts an actual Git archive through that parser.
