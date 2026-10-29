# 🚦 Optional YNAB gateway profiles

This is a source-only extension of the existing gateway release path. It neither
sets a repository variable nor authorizes activation. The current YNAB artifact,
capacity/provider/credential/client gates remain blocked; `env-prod` is held.

The permanent repository variable `YNAB_ROUTE_PROFILE` selects `base` (unset or
empty), `disabled`, or `enabled`. It is configuration, not a per-release approval
variable. Owner promotion of reviewed source to `env-prod` remains the gateway
authorization; no second reviewer, GitHub Environment or Deployment API is added.
Both credential-free authorization and execution validate the profile. All owner,
branch/source/workflow, fingerprint and key-loading checks remain in force.
Arbitrary workflow writers retain repository-secret privilege as documented.

## 📦 One supported bundle and transaction

`gateway_transport.py` archives the reviewed base mount trees and the exact
selected vhost blob. It flattens that vhost into `nginx/vhosts/zz-ynab.conf`, so
the same four read-only gateway mounts and original default-host order remain.
It never copies optional fixture exceptions, extra include wrappers or an app's
Compose definition. A strict versioned marker binds profile and vhost SHA-256.
The existing extractor rejects malformed/mismatched profiles before activation.

Only `enabled` adds the pre-existing external `ynab_mcp_private` network and exact
proxy `172.30.89.2`; Notoli's `172.30.88.2` trust and every existing network object
remain exact. No network is created/repaired. The gateway journal stores profile,
matched configuration and YNAB route-network/app identities. Normal releases and
recovery select topology validation from the accepted/target profile instead of
mistaking the approved fourth network for drift or silently dropping it.

App releases take the existing maintenance lock shared plus their exclusive app
lock; gateway releases retain the existing exclusive lock. Nothing changes the
v1 SQLite transaction or its application consumers.

## 🛑 Protected transitions and independent updates

First accept `base → disabled` before adding public DNS. The tombstone's origin
TLS/410 check requires no public DNS or running YNAB backend. After separately
approved DNS/TLS, app, issuer/client and artifact/capacity acceptance, the owner may
select `enabled` and promote reviewed source. First exposure checks both verified
origin and public TLS, the real anonymous 401 challenge and exact resource metadata.
`base → enabled` is rejected. After introducing the hostname, an implicit return
to `base` is rejected: retain the 410 tombstone through disablement and rollback.
Rolling back the first disabled baseline to an unprotected base is prohibited;
use a reviewed forward fix while retaining the tombstone.
If the first disabled activation is interrupted or fails after mutation, recovery
retains its syntax-tested disabled candidate. The private result is `protected`;
it has no unprotected predecessor to restore. An ambiguous Docker timeout still
retains the barrier until explicit owner recovery.

For an already enabled profile, later gateway-only updates allow a private
uncached 502/503 from a stopped YNAB backend. This preserves independent gateway
and app recovery while keeping the dedicated route fail-closed. Existing Notoli/
MacroMapper readiness remains mandatory. Restoring `disabled → enabled` performs
strict exposure checks again. No financial or authenticated API call is a gateway
readiness probe; the authorization server is never contacted by these probes.
Normal host validation requires the YNAB gateway endpoint. Transaction/recovery
checks explicitly allow an absent endpoint only when the exact project-owned
gateway container is stopped and still configured for the route network. Missing,
foreign, running-but-detached or reconfigured containers fail closed. This narrow
exception does not bypass the strict 401/metadata checks before first exposure.

During interruption, retain the journal barrier and inspect the host before the
existing explicit owner recovery. The route-network ID must remain unchanged.
An independently approved app update may change container identities before
recovery; refresh that baseline under the exclusive host lock, then verify it is
unchanged throughout the gateway-only recovery. Never recreate the route network
or retry an ambiguous Docker mutation.

The read-only host checker remains strict by default. For an accepted enabled
profile use `python3 scripts/check_host.py host --ynab-enabled`; it validates exact
known members, private subnet, IPv4 address and unchanged Notoli trust. This flag
does not authorize deployment or allow arbitrary extra networks.

## 🧪 Validation

`test_gateway_profiles.py` checks credential-free selection, protected
transitions, actual Git archives through the strict extractor and Compose
validator, marker corruption, explicit network/trust policy and safe health
responses. Existing real Nginx ingress/DNS/disable tests exercise the same vhost
bytes; existing gateway transaction/recovery tests retain default behavior. Run
the full root suite, release-manifest check, actionlint and ShellCheck before PR.
