# 🚀 YNAB and shared MCP first activation

This is the ordered operator procedure for #56/#62/#71. It composes the existing
gateway, issuer and YNAB controllers; it is not a new deployment framework.
Record the exact approved source, registry digests, operator and resulting
acceptance on #56. Source review alone does not authorize host operations.
The owner's direct coordinated-deployment instruction is recorded separately
from the architecture decision. Do not request an already recorded blanket
approval again or extend it to a paid resize, new host or financial writes.

## 📋 Before the maintenance window

- Complete Required CI, all three repository reviewers and Codex review for the
  exact source. Keep the shared release pin identical in Notoli, MacroMapper and
  FullStackTemplate; verify each application's own policy and deployment suite.
- Resolve all production images to immutable registry digests. Use the unchanged
  Oliver source/lock pin and the reviewed gateway, egress and issuer recipes.
  Follow [artifact security](ynab-artifact-security.md); unpublished local image
  IDs and saved scan reports do not constitute production artifact acceptance.
- After final source review, publish the issuer, gateway and egress images to
  their documented GHCR repositories. Verify each published manifest digest,
  Linux/amd64 platform, local image ID and exact repository `RepoDigests` match.
  Record all three references privately and sanitized digests on #56. Require
  the fresh issuer image gate as well as the paired YNAB gate under their release
  locks; a successful scan of one role cannot approve another image.
- Reconfirm the existing host, five running containers, accepted gateway record,
  no pending operation, exact networks, origin certificate/key access and public
  and origin HTTPS health. Capture private recovery evidence without printing
  environment values, credentials or database contents.
- Prelog each Cloudflare/DigitalOcean request and its purpose in KnowledgeVault,
  then append its result and any mutation. Report sanitized changes on #56.
- Refresh disk and representative-load capacity. Keep at least 512 MiB available
  to the host; before a scanner capped at 512 MiB with no swap, require at least
  1024 MiB available. Reserve archive/cache space while preserving the host's
  20% disk floor. Run scans and service startup sequentially. Resource failure
  stops the operation; it does not authorize a resize or relaxed security gate.

The expected new host resources are the independent issuer container and SQLite
directory, YNAB gateway and egress containers, and four fixed bridges:
`mcp_auth_private`, `ynab_mcp_private`, `ynab_mcp_egress_private`, and
`ynab_mcp_egress_public`. Confirm their exact names/IPAM against the canonical
Compose and network guides before provisioning. Existing network objects and
Notoli's `172.30.88.2` proxy trust remain unchanged. MacroMapper retains its
existing `172.20.0.3` ingress peer. Reuse the existing certificate only after
verifying coverage for both new hostnames.

Before service staging, provision these four external networks as an explicit
operator step after checking host/Docker/VPC subnet overlap. Use the exact IPAM,
gateway, bridge/internal and IPv6 settings in the network guides. Verify empty
initial membership or the exact accepted members, then record each network ID.
Existing objects must match; do not delete, rename or silently repair them.
Controllers validate and reuse these objects but never create them.

## 🛑 Establish the disabled public baseline

1. Record the exact gateway upgrade and its brief shared-proxy interruption.
   The reviewed candidate uses official Nginx 1.31.8 Alpine slim; historical
   Debian/cutover digests are recovery evidence, not current scan acceptance.
2. Through the existing owner-promotion path, accept both `YNAB_ROUTE_PROFILE`
   and `MCP_AUTH_ROUTE_PROFILE` as `disabled`. Follow
   [gateway profiles](gateway-profiles.md) and [gateway releases](gateway-releases.md).
   Verify origin TLS and uncached 410 on every documented disabled route, plus
   ordinary Notoli/MacroMapper health. Do not introduce DNS before this baseline.
3. Add only explicit proxied DNS records for `auth.judeandrewalaba.com` and
   `ynab.judeandrewalaba.com`, pointing at the verified existing origin. Retain
   Full (strict). Check public TLS and the same 410 responses. Do not add a
   wildcard, Access application, Worker or broad WAF/cache exemption. Capture
   prior DNS values/TTL (or absence), exact target/proxy state and reversal.
   Verify effective edge no-store/cache behavior and rule precedence. If the
   existing policy does not provide the required bypass, record and apply only
   the host/path-scoped MCP/discovery bypass in the ingress contract, then
   verify it. Do not weaken unrelated routes or claim cache acceptance from DNS.

## 🔑 Initialize the issuer privately

Provision protected, independent Django and signing-key files, the reviewed
`MCP_AUTH_SIGNING_KEY_ID` and the issuer data directory through the approved
private operator channel. Keep the key ID matched to the gateway's offline
public key. Follow
[issuer releases](mcp-auth-releases.md) for staging, fresh image assessment,
initial promotion and journal-safe recovery in the bounded persistent unit.
Both hostnames remain disabled during migration and registration. A migrated
empty issuer is privately ready; that does not prove registration or consent.

Use the existing [closed management commands](../services/mcp-auth/README.md)
under the maintenance/app lock to bootstrap the owner and register distinct
`ynab-chatgpt` and `ynab-codex` clients. Obtain actual callback URIs from each
client; do not guess ChatGPT callbacks or substitute localhost for a literal
Codex loopback address. Protect temporary password inputs and the emitted UUID.
Do not retry an ambiguous account/client mutation; inspect its outcome first.
The order is initial controller migration and private readiness, then
`bootstrap_mcp_owner`, then two `register_issuer_client --resource ynab` calls
with `--client chatgpt` and `--client codex`, the same `--owner-subject`, and
their respective exact `--redirect-uri` values. Retain private command outcomes.

The two YNAB clients use the same explicit owner UUID and exact YNAB resource.
Prepare the matched gateway identity file and offline issuer public key. Keep
the YNAB personal token in its existing protected token-file path; never copy it
to an issue, shell argument, Actions log or ordinary Compose environment.

For later token replacement, the owner uses YNAB web **Account Settings →
Developer Settings → Personal Access Tokens**. Generate and store a replacement
privately; revoke the superseded token on that same page after the matched
service change. The current prepared token does not need to be regenerated for
this rollout. YNAB's personal token is distinct from the short-lived client OAuth
tokens issued here. See [YNAB's official token instructions](https://api.ynab.com/#personal-access-tokens).

## 🔌 Activate and accept YNAB

1. Follow [YNAB releases](ynab-releases.md) to stage and promote the paired
   gateway/egress artifacts with fresh scans, matched private files and unchanged
   companion identities. Confirm `YNAB_ALLOW_WRITES=0` in effective runtime.
2. Promote `MCP_AUTH_ROUTE_PROFILE=enabled` with `YNAB_ROUTE_PROFILE=disabled`;
   verify issuer discovery and login over public and origin TLS. Then promote
   `YNAB_ROUTE_PROFILE=enabled` while keeping `MCP_AUTH_ROUTE_PROFILE=enabled`
   through the same reviewed gateway path. Never select `base` or combine
   enabled/disabled overlays for one hostname. Require the real anonymous 401 challenge, exact
   resource metadata and private no-store policy. Keep ordinary app checks green.
3. In **both ChatGPT and Codex**, configure the remote YNAB endpoint with its
   registered client, complete owner login/consent and initialize a fresh MCP
   session. List tools, prove write/admin tools absent, and perform a minimal
   read such as budget-list counts. Select the intended budget in the client;
   do not invent an unsupported upstream budget environment variable.
4. Verify client/resource separation and revocation using the maintained OAuth
   flow. Record only statuses, counts and timing in acceptance evidence. Never
   log token values, financial records or raw tool payloads. Offline YNAB access
   tokens can remain valid for their bounded 900-second lifetime after grant
   revocation; use the disabled route for immediate access containment.

For Codex, the registered public client is `ynab-codex`, without a client secret.
Use the current CLI's explicit client/resource options:

```sh
codex mcp add ynab --url https://ynab.judeandrewalaba.com/mcp \
  --oauth-client-id ynab-codex \
  --oauth-resource https://ynab.judeandrewalaba.com/mcp
codex mcp login ynab --scopes ynab:read
```

Register the exact callback shown by the installed client; callback paths may be
server-specific. An OAuth error before registration is not an acceptance result.
Keep the literal loopback hostname and path; do not replace them with `localhost`.
See the [official Codex MCP setup](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
For ChatGPT, use its remote MCP/custom connector setup with this same endpoint,
OAuth and the distinct `ynab-chatgpt` public client. Copy the actual callback from
that client's setup screen. If the account's client does not expose the necessary
custom MCP/OAuth controls, record that capability blocker; do not substitute an
API token or claim the Codex result proves ChatGPT support.

Owner interaction is required for actual client login/consent. A synthetic token
exchange, direct stdio test or private health probe cannot substitute for either
client's real acceptance. Keep #62 open until both clients are proven.

## 🧩 Independent application follow-through

After YNAB acceptance, follow Notoli #973's MCP-only migration and its app-owned
runbook. Register the dedicated introspector/client resources, explicitly link
the issuer UUID to the existing app user, then promote the reviewed app release.
Verify live permissions, ordinary website/REST login and reconnect behavior.
Do not infer identity from matching email or username.

Then follow MacroMapper #284's app-owned MCP rollout, including its pre-staged
disabled-policy recovery tool and exact proxy trust. Retain independent images,
databases and release locks; do not deploy both applications concurrently.
FullStackTemplate receives reviewed source/parity updates only, not a new live
application. Record all final source/pin/acceptance links on template #259.

## 🛟 Failure, rotation and closure

Use the documented 410 profiles for immediate public containment. Retain the
hostname tombstones; never silently restore `base`. Preserve every pending
barrier and inspect the persistent unit before explicit recovery. The issuer
controller restores the full SQLite namespace, invalidates grants/sessions and
enforces its durable YNAB JWT quarantine; YNAB's stop-only path never restarts an
unapproved image. Never replay ambiguous Docker mutations or financial requests.
Before issuer migration/restore, both profiles must be accepted `disabled` and
every required origin route must return verified uncached 410. Restoring bytes
extends the durable quarantine by at least 905 seconds; keep that record and
both route barriers intact. Re-expose YNAB only after its recorded deadline has
expired, recovery is accepted and normal issuer/client/image checks pass. Never
delete the record, shorten the interval or substitute a guessed wall-clock wait.

Token replacement/revocation, signing-key rotation and account recovery use the
matched private-file and containment procedures in the linked release guides.
Use the existing protected backup/monitoring processes; do not add a new daemon
or platform for this rollout. After the window, verify expected running images,
no pending barriers, ordinary app health, both client reads, memory/disk headroom
and retained recovery evidence. Record any unresolved operator work on #56.
Close implementation/acceptance tickets only for work actually verified.
