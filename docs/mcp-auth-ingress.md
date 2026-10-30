# 🔐 MCP authorization ingress and containment

The separately released authorization service uses the existing shared gateway
and a fixed `auth.judeandrewalaba.com` hostname. Its optional profile is inactive
by default. This source does not provision DNS, networks, keys or credentials.
The exact service/storage/key/DNS delta remains subject to the owner decision in
[#56](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/56#issuecomment-6511946488).

## 🧭 Fixed route and trust

Only the enabled profile attaches ingress to pre-existing internal bridge
`mcp_auth_private`, subnet `172.30.92.0/29`, gateway `.1`, ingress `.2`, service
`mcp-auth-server` `.3` with alias `mcp-auth:8000`. No host backend port is published.
Existing app networks and Notoli's exact `172.30.88.2` trusted proxy are unchanged.
MacroMapper's existing ingress peer is preserved and made explicit as
`172.20.0.3` on `macromapper-ingress`; backend `.2` and frontend `.4` retain their
current addresses. New gateway candidates must keep `.3`, which MacroMapper's
application-owned MCP proxy guard trusts. No network or container is renumbered.
Historical accepted models with an unspecified DHCP attachment remain readable
without rewriting their configuration/recovery hashes. Their baseline/restore
website checks are allowed only while MacroMapper MCP is disabled; they cannot
claim or replace an enabled MCP route. A failed strict trust check retains the
recovery barrier rather than adopting another address.
Host checks allow Docker's absent or empty-string `IPRange`; nonempty/null ranges,
auxiliary addresses, extra IPAM entries, unexpected members and wrong gateways fail.

The fixed public allowlist is:

- `/.well-known/oauth-authorization-server`
- `/o/authorize/`, `/o/token/`, `/o/revoke_token/`, `/o/introspect/`
- `/o/authorized_tokens/` and `/o/authorized_tokens/SLUG/delete/`
- `/accounts/login/`, `/accounts/logout/`, `/accounts/password_change/`,
  `/accounts/password_change/done/`

Query strings remain available on the library auth/account endpoints. Encoded
path aliases, additional path segments, signup/DCR/admin, OIDC and public health
routes are rejected. The application serves these library pages without a public
static route. YNAB validates a privately pinned public signing key; this route does
not invent a public JWKS endpoint.

Nginx fixes Host and forwarded scheme/client to its own observed values, strips
incoming forwarding/user/app-key claims and preserves browser cookies and Basic
credentials needed by the maintained authentication libraries. Requests are
bounded to 32 KiB, DNS and local connect deadlines to two seconds, and upstream
read/send to 30 seconds. Authorization access logs and raw request error logs are
disabled; no-store applies to redirects, errors and proxied responses.

The gateway reads Notoli's explicit live `DJANGO_MCP_AUTH_MODE` for readiness.
Missing mode preserves legacy checks; unknown or duplicate settings fail. Central
mode requires the retired local issuer to return uncached 410 and Notoli's own
resource metadata to advertise only the fixed shared issuer. It never contacts
the authorization service with an app credential or changes normal app login.

MacroMapper's exact `/mcp` and two metadata paths now use its existing backend
and route network, with the existing MCP transport/header/no-store snippets.
A disabled application registry must return backend 404, not a frontend page;
`/mcp/` is rejected. This routing source does not enable the registry, create a
network, or change ordinary REST, frontend or meal-estimation behavior.

Central Notoli or enabled MacroMapper requires an accepted authorization route.
An active consumer cannot introduce `base` or replace an unaccepted issuer with
its first disabled baseline. Enabled-route acceptance always checks real issuer
metadata with strict origin/public TLS while these consumers are active, even
on repeat gateway updates; unavailable upstream 502/503 is never called ready.
Explicit `enabled → disabled` or repeated disabled maintenance remains supported
and records the issuer as unavailable, so database containment stays possible.
YNAB's independently configured issuer remains subject to its own identity/client
acceptance contract.

## 🛑 Accepted state before database operations

`scripts/mcp_auth_containment.py` runs under the app controller's shared host
maintenance lock and exclusive auth lock. `baseline()` reads the accepted gateway
record, verifies its live runtime and both recovery/mounted configuration hashes,
matches both route markers, and captures the four existing apps, certificate
identity and any accepted YNAB release/network IDs. It rejects pending gateway or
YNAB journals and unaccepted YNAB containers. The auth service's own runtime/data
is excluded because its controller owns that transaction.

`require_contained()` requires both profiles to be accepted `disabled` tombstones.
It uses the operator-owned `/opt/host-ingress-deploy/origin-ca.pem` trust anchor,
verified hostname/SNI and loopback TCP to require uncached 410 responses from all
authorization endpoints plus `/mcp` and YNAB resource metadata. No boolean,
candidate certificate, disabled TLS verification or saved approval substitutes
for those observations. Missing trust evidence fails closed.

The simplest supported auth release sequence is: accept both disabled gateway
profiles, run the reviewed app-only migration/recovery with baseline equality,
then separately expose accepted services. Source checks and these probes make no
financial API call and do not prove real ChatGPT/Codex consent or client acceptance.

Restoring issuer state invalidates grants/sessions and starts a private durable
905-second YNAB quarantine before database bytes change. Offline YNAB JWTs may
remain valid for 900 seconds plus clock tolerance; route re-exposure must wait
until that deadline and the auth recovery barrier are clear. The gateway checks
the protected record before starting an enabled route, including recovery from
disabled to enabled. It cannot clear/reset or override the record. Disabling
routes does not depend on scanner availability or quarantine expiry.

## 🧪 Verification

Run gateway/profile/recovery, containment and both existing ingress suites on a
disposable local/CI Docker daemon. `test_gateway_auth_ingress.py` additionally
uses the real pinned Nginx image with synthetic certificates/HTTP providers to
verify the path allowlist, secure-cookie/Basic forwarding, body bounds, no-store,
absent-service behavior and explicit 410 recovery while companion IDs/networks
remain unchanged. These fixtures never run the production cutover guide.
