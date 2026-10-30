# 🔌 Optional application MCP ingress

Enable this profile only when an application's reviewed ASGI server and OAuth
client policy are ready. Notoli is enabled today; MacroMapper remains ordinary
REST/frontend with no advertised MCP. FullStackTemplate is an onboarding example,
not a third production instance. Application tools, users, OAuth grants and domain
authorization belong to their application repository.

## 🌐 Routing and security contract

Each enabled app vhost defines its own `$app_backend`, `$app_frontend`, fixed
`server_name`, certificates and reviewed network attachment. At server level,
include `nginx/snippets/mcp-locations.conf`. The inactive
[example vhost](optional-mcp.conf.example) contains no production activation.
The include preserves exact `/mcp` without a trailing-slash rewrite, HTTP/1.1,
buffering off, empty Connection and a 120-second upstream **idle** read timeout.
It forwards `/.well-known/*` to the same backend. The backend OAuth endpoints
`/auth/mcp/authorize/`, `/auth/mcp/token/`, `/auth/mcp/revoke/` and the JWT-only
connection-management API `/auth/mcp/connections/` use private `/auth/` forwarding.
The separate browser pages `/connections` and `/connections/authorize` stay on
the frontend; they call those backend APIs. JSON Streamable HTTP requires no WebSocket
route. Request bounds and ASGI lifespan/session handling are app responsibilities.

Private routes and discovery disable proxy caching, hide upstream cache policy
and emit `Cache-Control: no-store`, including failures. Fixed Host and replaced
forwarded client/proto headers prevent spoofed metadata. Application ASGI trusts
only individually reviewed gateway peer addresses on a private backend network;
never copy Notoli's subnet into a new app or trust a wildcard/CIDR. Keep Notoli's
existing `.2` gateway/`.3` backend and all current network objects unchanged.
Do not publish backend ports. Docker/root administrators remain privileged.

Preserve query-free access logs and disabled raw-request error logging: OAuth
codes/state/tokens must not leak through upstream errors. Forward OAuth queries
and bodies exactly. Review edge cache, redirect, WAF/challenge and rate-limit
policy before enabling a new domain; discovery/MCP cannot require an interactive
challenge. Keep full strict TLS. This extraction adds no DNS/certificate/edge rule.

## 🚦 Readiness and onboarding

Use the application release standard's existing app-specific JSON/header
assertions; there is no new shared engine or cross-app release dependency.
Keep normal frontend HTML and unauthenticated API JSON checks. For an enabled
profile add issuer metadata, exact protected resource metadata and `/mcp` 401
with the resource-metadata Bearer challenge. Notoli's current policy already
does this. An ordinary app retains ordinary readiness and must not advertise
OAuth metadata/MCP challenges; an unknown-path SPA HTML response is not discovery.

Before activation, review the app registry/scopes/consent, independent secrets,
HTTPS origin/frontend settings, OAuth migrations, ASGI command and exact trust,
network membership/capacity, vhost and app readiness policy. Register only an
exact HTTPS public-client callback with S256 PKCE; no password/implicit grants
or dynamic registration. Apply app-level ownership/current membership on every
tool operation. Infrastructure never creates accounts, grants or business tools.

## 🧪 Verification and recovery

Disposable Nginx tests exercise two enabled app vhosts and an ordinary app,
discovery/auth forwarding, exact resource/challenge routing, no-store failures,
65-second upstream responses, header replacement, query-safe logs and preserved
companion identities during proxy handoff/reversal. Application suites establish
real JSON discovery, initialization, tool schema/annotation and OAuth behavior;
the Nginx stub is routing evidence, not authenticated application acceptance.

Record the designated operator, exact reviewed sources and scope on #4. Passing
source CI is not production acceptance. Promote using the normal reviewed gateway
and independent app workflows under the existing maintenance lock. Verify public
and origin HTTPS readiness, discovery/challenge, ordinary app behavior, immutable
images, unchanged networks/certificates and no pending/failure barrier. Compare
with a sanitized baseline. Use unauthenticated probes unless separate account/
grant/business-write acceptance is explicitly authorized. Do not revoke the
owner's existing connection to test revocation.

On failure stop and inspect the exact attempt, journal and barrier. Use the
affected component's explicit retained-source/image recovery from
[gateway releases](gateway-releases.md) or the app release guide. Preserve current
databases and private recovery evidence. Never rerun the initial cutover, rebuild
shared networks, prune global images or blindly retry. Remove a newly activated
optional profile through a reviewed component release; retained OAuth tables and
grants require deliberate application cleanup. See [onboarding](onboarding.md)
and [the release standard](app-release-standard.md).
