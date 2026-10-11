# Shared ingress contract v2

**PROPOSED — explicit owner architecture approval required.**
Prepared by Agent 5 on 2026-10-11. Agent 3's
[v2 feasibility review](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4#issuecomment-6111422055)
finds the interface feasible against the observed VM with no required
architecture change. Implementation tests and production prerequisites remain
open; this is ready for owner architecture review, not production approval.
The canonical discussion is [Infrastructure #4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4).
This document is a review proposal, not executable deployment instructions.
Architecture approval, each exact PR merge, and each production operation are
separate gates. No shared-interface implementation is finalized before approval.

## Reconciliation and source evidence

The [owner directive](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4#issuecomment-6111334394)
consolidates Agents 1/2/4 into Agent 5 and retains Agent 3 as independent VM
inspector and sole separately authorized operator. The infrastructure repository
is already selected; the former proposed `host-infrastructure` repository is
superseded. Advanced automation in Infrastructure #5–#9 is deferred.

Carry forward, rather than discard:

- [Historical VM audit, 01:21–01:22 PDT](https://github.com/VanillaIceCube/Notoli/issues/904#issuecomment-6107091928).
- [Notoli reconciliation](https://github.com/VanillaIceCube/Notoli/issues/904#issuecomment-6107111199).
- [Prior v1 proposal](https://github.com/VanillaIceCube/Notoli/issues/904#issuecomment-6107124549),
  [MacroMapper conditional review](https://github.com/VanillaIceCube/Notoli/issues/904#issuecomment-6107138862),
  and [release-staging clarification](https://github.com/VanillaIceCube/Notoli/issues/904#issuecomment-6107132678).

Agent 5 inspected Notoli `main` at
`b4586362d5797e6da44f0a6dcaaaa37ada747113`, MacroMapper `main` at
`a510a3a5ad9cc3f70304f451bbbac72f3cc7c139`, their Compose/vhost/release code,
Notoli ASGI trust middleware, MacroMapper production settings, and existing
PRs [Notoli #905](https://github.com/VanillaIceCube/Notoli/pull/905) and
[MacroMapper #241](https://github.com/VanillaIceCube/MacroMapper/pull/241).
Both PRs remain unmerged. Their existing CI results are not runtime acceptance.

The [refreshed VM audit, 09:49–09:53 PDT](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4#issuecomment-6111383750)
confirms no topology/image drift: both apps already running, with `notoli-proxy`
owning 80/443 and mounting MacroMapper's vhost from its release directory.
Notoli frontend also publishes 3000. This establishes the migration baseline,
not approval of previous deployment or feature acceptance. Agent 3 reports
Engine 28.2.2, Compose 2.40.3, linux/amd64 images, successful external-network
syntax validation, and all four unique upstream names resolving from the
current proxy. Notoli's exact source revision is still unknown; preserve
observed image digests for recovery. Repository code cannot establish live state.

## Ownership and files

This repository alone owns the replacement Nginx Compose definition, vhosts,
network registry, offline validation, and host cutover/recovery runbooks.
Proposed runtime directory `/opt/host-ingress`, project `host-ingress`, service
`proxy`, container `host-ingress-proxy`. The website remains an independent app;
this change does not invent or transfer an apex-domain route. Inventory any
additional hostname routing before enabling a default-host rejection policy.

Keep app projects `notoli` and `macromapper`, their existing container/service
names, and their current database locations. Notoli retains
`/root/apps/notoli/db.sqlite3`; MacroMapper retains
`/opt/apps/macromapper/db.sqlite3`. No storage relocation or schema change is
part of ingress transfer. Application production definitions become explicit
app-only Compose files, separate from local standalone proxy configurations.
Always specify project and files; do not accidentally discover the legacy
Notoli override. App releases must not use `down`, `--remove-orphans`, proxy
reload/recreation, shared-network deletion, or host-wide pruning.

Host route-network lifecycle belongs to the operator. Application releases
reference route networks as external and never provision or repair them.
Docker/root access remains privileged; these conventions do not provide
adversarial tenant isolation from an administrator.

## Networks and names

Adopt these historical networks in place, subject to Agent 3's refreshed
membership/IPAM verification. Keep existing labels; do not recreate or rename
networks merely to transfer lifecycle ownership. Validate external network
properties separately: an external Compose declaration cannot assert IPAM.

| Existing network | Allowed members after transfer | Address and upstream contract |
| --- | --- | --- |
| `notoli_backend_private`, internal, `172.30.88.0/29` | Ingress and Notoli backend | Ingress `172.30.88.2`; backend `172.30.88.3`; `notoli-backend:8000` |
| `notoli_default`, `172.18.0.0/16` | Ingress and Notoli frontend | `notoli-frontend:80` |
| `macromapper-ingress`, `172.20.0.0/16` | Ingress and MacroMapper frontend/backend | `macromapper-frontend:80`, `macromapper-backend:8000` |
| `notoli_backend_egress`, `172.19.0.0/16` | Notoli backend only | Existing outbound path retained; app-owned |
| `macromapper_default`, `172.21.0.0/16` | MacroMapper frontend/backend | Existing egress and frontend's generic `backend` alias retained; app-owned |

Ingress joins only the first three networks. MacroMapper never joins Notoli
networks. The Notoli frontend never joins its private backend network. Both
app backends remain unpublished. Existing unique container names are the
verified DNS names for ingress-only transfer; recheck their resolution and
network membership immediately before cutover. Future app definitions explicitly
retain unique aliases without recreating apps during the ingress-only step.
Generic `backend`/`frontend` names are never used by shared ingress.

Port 3000 disposition is a separate operator/owner decision after consumer
inventory. Do not silently remove it during ingress transfer. The subsequent
app-only Notoli release should remove it or bind it to loopback once approved.

## Routing and proxy trust

Serve the existing `notoli.judeandrewalaba.com` and
`macromapper.judeandrewalaba.com` vhosts on 80/443 with canonical HTTPS redirects.
Retain 25 MiB body limits and existing slash redirects for `/api`, `/auth`, and
`/admin`. Preserve path, query, and encoded components when proxying.

| App | Direct backend routes | Frontend routes |
| --- | --- | --- |
| Notoli | Exact `/mcp`, `/.well-known/*`, `/api/`, `/auth/`, `/admin/`, `/static/admin/`, `/static/rest_framework/` | `/` and SPA deep links, including `/connections*` |
| MacroMapper | `/api/`, `/auth/`, `/admin/`, `/static/admin/`, `/static/rest_framework/` | `/` and SPA deep links |

Use Docker DNS `127.0.0.11`, a short cache (`valid=10s`, `ipv6=off`), variable
upstreams, and original `$request_uri`. A missing app must not prevent Nginx
startup or serving the other app; container recreation must recover without an
ingress reload. Test actual behavior, including URI handling and DNS expiry.

Set canonical Host and overwrite forwarded scheme/client with the ingress
scheme and immediate peer (`$remote_addr`). Clear incoming `Forwarded` and
`X-Forwarded-Host`; do not authenticate incoming client-supplied forwarding
chains. Notoli retains `DJANGO_TRUSTED_PROXY_IPS=172.30.88.2`, Uvicorn
`--no-proxy-headers`, ASGI exact-peer validation and forwarded-header stripping,
and Django's existing rejection of forwarded host/proto trust. MacroMapper
retains its production Host/origin/cookie settings and restricted backend
reachability. Its current appended X-Forwarded-For becomes an overwritten
peer address; prior source review found no authorization dependency on it.
Cloudflare visitor-IP restoration is outside this change.

Keep `/mcp` exact, HTTP/1.1, empty Connection, buffering off, and 120s read
timeout. Preserve existing frontend upgrade behavior separately. Explicitly
test Nginx header inheritance in every location, especially MCP/upgrade
locations with local `proxy_set_header` directives. Disable backend proxy
caching and return `no-store` for authenticated auth/API/admin/MCP responses;
discovery remains public. Do not log OAuth codes/tokens or sensitive query
strings in new ingress logs. Verify the logging policy in the config tests.

## TLS and secrets

Reuse the currently running Nginx digest, verified by Agent 3 as linux/amd64:
`nginx@sha256:df221db836e1754089190208cee7eeda94f233197056426eda74a43ab1abeac2`.
Do not combine ingress transfer with an image upgrade. Initially mount
`/root/apps/notoli/certs` read-only, now administratively host-owned. App release
bundles must stop uploading certificates or modifying this directory before
they are re-enabled. A later certificate relocation/rotation is separate.

Historical certificate metadata covers apex plus wildcard through 2041-02-04.
Agent 3 confirmed the key is 0600, owned by uid/gid 1001:1001, with the current
root-default Nginx master able to use it. Do not combine transfer with a
rootless-user change. Recheck metadata/access before cutover; no private keys or environment values
enter Git, comments, CI artifacts, or logs. Production credentials stay per app.
Use raw env-file semantics to preserve literal credential bytes, validated
against the installed Compose version. Private directories/files target
0700/0600 with runtime-compatible ownership; do not blindly change existing DB
ownership. Cloudflare Full (strict), caching/challenges, origin firewall rules,
and production SSH/GHCR credential capability remain separately verified
operator prerequisites, not conclusions from public HTTPS 200 responses.

## App release and recovery interface

Each app owns its CI build and app-only release. Reviewed `env-prod` source
produces full SHA image tags on CI, with actual digests recorded before
activation. Never select `latest` for production. No workflow dispatch or
release-branch push occurs without specific owner authorization.

1. Upload to a private, unique incoming directory containing source SHA plus
   run/attempt identity; a repeated SHA must not overwrite another attempt's
   staged or active bundle. Validate a complete manifest before activation.
   Do not upload any app/infra files over active configuration before locking.
2. Serialize CI with `cancel-in-progress: false`. Take a stable per-app host
   lock outside replaceable release directories before validation/promotion,
   stopping writers, backup, migration, startup, checks, or recovery. Shared
   maintenance takes an exclusive host lock; app releases take a shared host
   lock as well as their app lock. Fix one lock acquisition order in code.
   Initial legacy workflows lack this protocol, so cutover requires an
   explicitly approved release hold and confirmation no deployment is running.
3. Check route-network/trust contract, paths, credentials without printing
   them, runtime ownership, disk and memory. Missing prerequisites fail before
   modifying services. Capture previous effective config, script, environment,
   image digests, database mount, and release record as one private recovery set.
4. Stop affected app writers and use SQLite backup, integrity validation, and
   an isolated restoration check before migrations. Existing DB files must
   never be truncated. A first-ever release must explicitly distinguish an
   absent database from a failed/missing backup of an existing deployment.
5. Promote only app-local configuration under the lock; run production checks
   and migrations; start only the selected app services. No shared vhost,
   certificate, network, or proxy mutation.
6. Use bounded read-only readiness and HTTPS checks with expected status/body
   and correct Host: frontend root, known unauthenticated API/auth behavior,
   and Notoli discovery plus MCP authentication challenge. Check a real Django
   route, not only the frontend or TCP listener. Fix exact commands/expected
   responses in implementation and operator review; no email, account creation,
   data writes, or billable AI calls in automatic release checks.
7. Only after success atomically mark current release with source/config SHA,
   actual image digests, backup reference and check result. Failed validation
   must not write a success record. Preserve recovery artifacts on every failure.
   Schema failure requires explicit matched configuration/image/DB recovery;
   image rollback alone cannot repair a changed schema. Restoring a snapshot
   can lose later writes and requires the approved recovery decision.

Retain prior verified images and recovery sets. No generic deployment engine
or automatic host cleanup is introduced. Exact lock paths/permissions and
recovery commands require Agent 3 feasibility and the later approved runbook.

## Migration order and reversal

Agent 3 must produce a separately approved command-level deployment plan.
This is the required order, not permission to execute it:

1. Validate current topology, routes, images, aliases, certificates, available
   capacity, recovery completeness and both apps' baseline behavior. Obtain
   consistent backups and prove isolated restore under authorized operations.
2. Establish the approved release hold for both apps; preserve effective base
   and override files, mounted vhosts and exact rollback images. Privately stage
   approved ingress and app-only candidates. Do not change app images/schema
   during gateway transfer.
3. In the approved maintenance window, disable old proxy automatic restart,
   stop it, and remove only the stopped legacy proxy container, as recommended
   by Agent 3. Inspect to confirm `.2` and 80/443 are vacant before replacement.
   Never remove app containers, networks or data for this handoff. Stopping
   alone is not treated as freeing `.2`. The exact removal/recreation commands
   still require disposable testing and the separately approved operator plan.
4. Start the replacement as sole 80/443 owner and sole `.2` proxy peer. Keep
   both current apps attached to their existing networks. Expect a brief outage
   to both sites. Verify routing and exact trust immediately, then Notoli
   discovery/challenge/login/consent/MCP and existing MacroMapper behavior.
5. On failure, stop/remove only the replacement, confirm endpoint/port vacancy,
   and recreate only the old proxy using the captured base+override, cached
   original image digest, no dependencies, no pull, and original restart policy.
   Never attempt both proxies at `.2`
   simultaneously. Do not delete adopted networks or restore a database merely
   for a proxy-only failure. Verify both apps after reversal.
6. After ingress acceptance, activate the approved Notoli app-only release and
   prove repeat deployment leaves ingress and MacroMapper unchanged. Then do
   the same for MacroMapper. It is already running; this is release isolation
   and acceptance, not an assumption of first installation. Re-enable releases
   only after shared mutation paths are gone and the maintenance lock works.
7. Retire old bridge files only when replacement and rollback are verified.
   Reboot, restore drills, email/AI and other mutating functional tests require
   inclusion in the separately approved operator plan.

## PR #239 disposition and PR ordering

| PR #239 component | Agent 5 recommendation |
| --- | --- |
| Production Django safeguards and tests | Keep |
| SHA selection, raw credentials, SQLite checks, ownership tests | Keep; strengthen recovery and readiness gates |
| Shared Compose profile/extends/reset layers | Simplify to explicit app-only production Compose after approval |
| MacroMapper-owned Notoli override/vhost and proxy reload | Replace with infrastructure ownership only after verified transfer |
| Standalone local Compose/proxy | Retain for local use, excluded from shared production release |
| Claim of approved/verified deployment | Correct in existing audit PR #241; source/CI never substitutes for live evidence |

A wholesale revert is not recommended: it would lose app/data safeguards and
restore prior deployment hazards. No approval of the merged bridge is implied.

Existing Notoli #905 removes host-wide pruning only; existing MacroMapper #241
records the audit only. They are independently reviewable and do not authorize
or complete ingress migration. Keep their PR history rather than duplicating.
This documentation PR presents v2 for architecture review. After v2 approval:

1. Infrastructure #1 implementation PR: gateway/network validation, disposable
   routing and failure tests, cutover/rollback runbook and onboarding checklist.
2. Separate Notoli #904 PR: app-only release/trust/data safeguards; include #905
   only after its independent approved merge or an explicitly reviewed stack.
3. Separate MacroMapper #240 PR: app-only release, removal of live shared-proxy
   responsibilities, locked staging/full recovery/readiness; retain #241 audit.

Review these together for interface compatibility; authorize each merge by
exact PR separately. Merging to main must not deploy. Do not promote any app
to `env-prod` during preparation; production activation follows the sequence
above and Agent 3's exact plan. Infrastructure tests remain basic validation;
do not implement the deferred bot/security automation stack.

## Validation and open decisions

Agent 3's review adds the following concrete implementation/runbook obligations
within v2's existing interface (no v3 required):

- Capture or revalidate the final matched recovery set after the release hold
  includes queued/in-flight CI uploads and manual operators. Keep the hold
  through acceptance or reversal; old workflows do not honor new locks.
- Preserve original project-directory/path interpolation when reconstructing
  legacy Compose from captured files. Verify expanded bind sources, including
  the MacroMapper vhost and effective cert directory, before cutover.
- Keep post-transfer app recovery app-only. Captured legacy scripts may
  recreate/reload ingress and must not be executed as app rollback procedures.
- Acquire the host maintenance lock before the app lock, using protected,
  stable, symlink-checked files in an operator-provisioned directory. Do not
  assume a predictable file in world-writable `/run/lock` is protected. Preserve
  the lock inode through promotion and hold it through recovery/success record.
- Validate actual staging/active filesystems before atomic promotion; bind
  app image digests across validation, migration and startup so a mutable SHA
  tag cannot select different content between phases.
- Prove capacity for simultaneous app releases allowed by shared host locks,
  or initially serialize releases operationally. Pin readiness expectations,
  retry limits and failure cutoff; rehearse endpoint conflict and reverse
  recreation on disposable infrastructure. Verify both apps before releases.

Implementation must prove real Compose expansion with synthetic secrets;
private network membership and `.2/.3` trust; no published backend ports;
Nginx syntax and HTTPS route/header/cache/URI behavior; missing-app startup;
DNS recovery after app recreation; release concurrency and failure recovery;
and app-only operations leaving the other app and ingress untouched. Use
disposable local/CI networks and test certificates, never the live VM.
Existing app proxy/settings tests remain part of applicable validation.

Before requesting production approval, resolve:

- Tested endpoint reversal and implementation of Agent 3's v2 conditions. The refreshed audit
  verifies versions, aliases and image architecture, but not a live handoff.
  Root can access current app paths; non-root deployment ownership/access
  remains unproven. Specify stable locks and reviewed privilege/ownership
  arrangements before release implementation is activated. Read-only
  feasibility is not a successful rollback rehearsal.
- Owner architecture approval and later each PR-specific merge approval.
- Named operational owner, maintenance window, port-3000 consumers/disposition,
  release hold and activation authority.
- Backup destination/credentials, retention and restore evidence. Proposed
  baseline: daily encrypted off-host backups, 7 daily + 4 weekly retained;
  no paid service or destination is assumed.
- Resource policy: proposed at least 20% disk free after staging/rollback
  retention, at least 512 MiB available under representative peak load, no OOM
  events or sustained CPU saturation; builds stay on CI. Historical idle
  1.1 GiB available (refreshed idle 1.2 GiB)/16 GiB disk free is not peak-load evidence. No third app
  until capacity review. Proposed log cap: 10 MiB × 3 per container.
- Cloudflare mode/cache/WAF and origin access verification; secret permissions,
  credential capability, monitoring ownership and actionable alert delivery.

Operational selections do not prevent reviewing the interface, but remain
explicit production gates. Any VM objection changing this interface requires
a numbered contract revision and renewed owner approval before implementation.
Issues remain open until observed production acceptance and recovery evidence.

Primary references: [Docker external networks](https://docs.docker.com/compose/how-tos/networking/#use-an-existing-external-network),
[Compose env files](https://docs.docker.com/reference/compose-file/services/#env_file),
and [Nginx proxy semantics](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass).
