# 🌐 Gateway and routing

This folder owns shared Nginx ingress, host topology verification and gateway
release/recovery. Apps retain their own data, credentials, OAuth issuers and
independent releases. [Architecture approval](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4#issuecomment-6111586759)
authorizes the technical contract; each merge and production operation retains
its separate authorization. Coordination, named operators and actual acceptance
belong on [#4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4).

| Task | Section |
| --- | --- |
| Release an adopted gateway | [Promotion and retry](#-promotion-and-retry) |
| Resolve a failed or interrupted release | [Recovery](#-failure-interruption-and-explicit-rollback) |
| Prepare a host or change credentials | [Prerequisites](#-approval-and-prerequisites) and [adoption](#-private-host-preparation-and-adoption) |
| Inspect networks and routes | [Structure and ownership](#-structure-and-ownership) |

For an adopted gateway, confirm reviewed source, owner authorization, the
accepted host record and completed setup before promotion. Keep `DEPLOY_ENABLED`
unset until prerequisites and initial adoption are ready. Source review and
merging `main` do not authorize the separate `env-prod` promotion.

## 🚀 Operations

The owner's [October 19 decision](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4#issuecomment-6273538610)
authorizes automatic gateway deployment when the owner promotes reviewed main
source to `env-prod`; no second reviewer or per-release approval variable is
required. Both the original actor and retrying actor must be the repository owner.
Manual retries retain owner authorization; initial host preparation and explicit
recovery have separate approved scope. Source/CI approval does not authorize promotion.
Nginx image upgrades require native-package security assessment plus applicable TLS,
proxy, gzip, DNS, MCP streaming and recovery evidence before promotion; retired root
fixtures cannot establish that acceptance.

Subsequent gateway releases use the procedure below. Preserve accepted recovery
generations; legacy proxy handoff is outside the ordinary release procedure.

<a id="-promotion-and-retry"></a>

### Promotion and retry

After source review/green CI, the authorized operator promotes that reviewed
`main` commit to `env-prod`. The push starts **Deploy gateway** automatically;
there is no second approval step. `main`/PRs never invoke deployment. Manual dispatch
must select **env-prod**, operation **deploy**, empty recovery field; it uses
the branch's exact current SHA, not a user-supplied revision. Each retry has a
new `<sha>-<run-id>-<attempt>` identity and revalidates the current branch/source.

Actions serializes runs with cancellation disabled. SSH uploads a bounded,
checksummed Git archive into private incoming storage. A persistent systemd
unit runs the transaction independently of the SSH session. Host commands and
probe suites have bounded deadlines; the unit has no automatic mutation cancellation.
Cancelling/losing the runner does not stop the host unit.
Do not cancel an active release as a recovery mechanism. Inspect its host
journal and systemd unit before another approved retry.

The exclusive lock covers topology validation, previous-state verification,
capacity, syntax checks, activation, bounded health, success recording and any
rollback. Capacity requires at least 512 MiB available memory and 20% free disk
(at least 1 GiB), rechecked after immutable image availability verification.
Cached matching repository digests are reused; only absent images are pulled. This is a
minimum check; representative host load and image/recovery retention budgets
remain operator prerequisites.

Candidate configuration lives in `releases/<identity>`, never overwriting live
mounted files. Compose is restricted to one immutable Nginx service, existing
external networks, `.2` trust address, original certificate path, listeners and
logging. Nginx syntax runs with no network or published ports. Activation uses
only `up --no-deps --pull never --force-recreate proxy`; no project shutdown,
network provisioning/removal, app restart, database restore or pruning occurs.

<a id="-failure-interruption-and-explicit-rollback"></a>

### Failure, interruption and explicit rollback

The release writes its recovery records in this order.

1. `attempts/<identity>/journal.json` records the previous gateway configuration,
   image, source, and runtime. It also records the app, network, and certificate
   identities and the Actions run.
2. Just before Docker recreates the proxy, the release durably writes that
   journal to `pending.json`. Its presence blocks a new release until the
   gateway is accepted or restored.
3. After the new gateway passes its checks, `current.json` records the accepted
   release. The controller writes the attempt result and removes `pending.json`.

Pre-activation rejection leaves the accepted runtime unchanged.
Failed activation/health automatically recreates only the captured previous
gateway, validates both apps again, and reports **failure**, even when recovery
succeeds. An indeterminate Docker activation timeout retains the pending barrier
instead of racing rollback against a still-running daemon request. Failed recovery
also keeps the barrier and private evidence. Verify the original host unit and
Docker request have finished before authorizing explicit recovery.

An interrupted mutation, including SIGKILL or host reboot, leaves the pending
barrier; a new deployment cannot bypass it. With separate recovery authorization,
dispatch **Deploy gateway** on **env-prod**, operation **rollback**, supplying
the exact failed/current release ID. The branch/source checks still select the
current env-prod helper; the recovery identity selects only retained host state.
Rollback uploads only the reviewed helpers; it neither builds nor uploads a
candidate source archive.
For SSH/Actions unavailability, the approved operator can invoke the same
reviewed helper on the host:

```sh
python3 nginx/gateway_release.py rollback --source <approved-helper-full-sha> \
  --id <retained-sha-run-attempt>
```

Only the matching pending attempt or the current accepted release's immediate
predecessor may be restored. Rollback takes the same exclusive lock and performs
syntax, invariant and health checks. No app database rollback is involved.
After accepted rollback, the host record identifies the restored source, not
the attempted promotion. Later app releases are allowed before an explicit
gateway rollback; their current identities are captured under the lock. Pending
recovery also refreshes app identities after reboot/restart, validates app trust
and network policy even if the gateway is absent or partially attached, and
rejects changed route-network IDs before recreating the gateway. The original
attempt journal remains historical evidence; the pending record holds the new
recovery baseline, which must remain unchanged through restoration.

<a id="-health-and-relevant-changes"></a>

### Health and relevant changes

Both the public edge and loopback origin verify HTTPS frontend HTML, JSON API
401 responses for both apps, Notoli issuer/resource discovery and the MCP 401
authentication challenge. Origin connections preserve hostname verification
and SNI with a separately provisioned CA if necessary. Redirects/challenges
cannot silently pass. Requests use `JudeGatewayRelease/1.0` and cache bypass
headers. Each complete suite has an 80-second process deadline, three attempts
and two-second intervals (244 seconds maximum); each socket has a five-second
timeout and responses are limited to 256 KiB. The former root ingress route/DNS suite has been retired; verify the
120-second backend/MCP timeout contract under separately authorized acceptance.

Restart policy compares the effective expanded Compose model, immutable image,
all `nginx/**/*.conf` bytes and certificate mount location to the **actually
accepted host record**, not the previous Git push. It normalizes release-directory
paths. Changes only to docs, workflow/helpers or `app-release/v1` produce an
`unchanged` attempt after baseline health checks; the gateway ID and running
source stay unchanged. Compose/Nginx byte changes restart after validation.
Unsupported payload files and Compose settings fail explicitly.

<a id="-evidence-and-retention"></a>

### Evidence and retention

Actions run status, summary and logs record the promoted source, unique
source/run/attempt identity, operation and explicit recovery target when present.
Only an accepted host response adds a verified `success`, `unchanged` or
`rolled_back` result with the actual running source. A successful unchanged
promotion does not claim the helper's promoted source is running. Explicit
rollback reports the restored source. No GitHub Deployment API records or
GitHub Environments are created or required.

The durable host `current.json` is authoritative for the accepted running source,
image digest, configuration identity, Actions run and recovery reference.
While `pending.json` exists, `current.json` describes the last accepted state;
inspect the pending attempt and actual runtime before asserting what is running.
Private attempt journals/results preserve promoted versus running identities.
Failed command context and bounded output are retained as mode 0600 files in
the private host `diagnostics` directory; Actions receives only the tool/phase
and exit code. Inspect those files on the host, never paste their raw contents.
Never publish full Docker inspect, journal/config contents, credentials or keys.
Failed/cancelled runners remain failed/cancelled in Actions, even if an independent
host unit later completes. The credential-free finalizer reports an unconfirmed
host outcome without overwriting earlier verified evidence. A hard runner loss
may prevent finalizer/summary delivery; Actions' conclusion and the host journal
remain the evidence. Inspect systemd and `pending.json`/`current.json` privately,
then record the **observed** running source under
the approved operator plan. A green job alone is not production acceptance.

Retain all incoming, release and attempt directories, previous images and
recovery records until operator-reviewed retention cleanup. No automatic
cleanup or off-host backup is included. Never remove a mounted/current release,
any pending attempt or its predecessor. Monitor disk space before future releases.
Production acceptance still requires the separately authorized first and second
independent release plus recovery evidence recorded on #4.

## ⚙️ Initial setup and historical compatibility

<a id="-approval-and-prerequisites"></a>

### Approval and prerequisites

Source changes land through reviewed `main` first, with explicit owner approval
for each merge; review alone does not authorize merging or the later production
promotion. If the owner explicitly
authorizes a narrow deployment experiment outside that path, return its changes
and history to `main` promptly through a reviewed PR before ordinary promotion
resumes. Compare both ancestry and file contents: promotion merge commits can
differ without introducing production-only code. Reconcile history without
discarding newer main changes or rewriting either protected branch. Intentionally
unreleased main work is permitted; hold `env-prod` until its prerequisites are
met rather than deploying unrelated features to obtain equal trees. See the
[shared policy](https://github.com/VanillaIceCube/FullStackTemplate/blob/main/.github/README.md#main-first-releases)
and [parity audit #87](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/87).

Keep repository variable `DEPLOY_ENABLED` unset until initial host setup
and adoption are ready. Initial setup remains an explicit owner operation. Configure:

- Protect `main` and `env-prod`, require reviewed green PRs for source changes,
  and restrict `env-prod` promotion to the designated release operator. Promote
  an existing reviewed `main` commit, never an independent production commit.
  A regular promotion merge may have a different commit ID only when its entire
  Git tree exactly matches current reviewed `main`; this includes workflows and
  release helpers, not only Nginx configuration. Divergent file contents fail.
- No GitHub Environment is required. The job restricts the repository, branch,
  original actor and retrying actor before loading credentials. A separate
  credential-free step verifies the exact promoted workflow/source through
  GitHub's API; the transport repeats those checks immediately before SSH.
  Its token needs only contents read; no Actions or Deployments write access.
- No `GATEWAY_APPROVED_SHA` variable is needed. The workflow verifies its exact
  checkout is still the current `env-prod` head and contains reviewed source.
  Set repository `DEPLOY_ENABLED=true` after prerequisites and initial
  baseline adoption below pass. Setting the flag does not replay a skipped run.
- Repository Actions secret: `DEPLOY_SSH_KEY`. Repository Actions variables: `DEPLOY_HOST`,
  `DEPLOY_USER`, `DEPLOY_PORT`, `DEPLOY_HOST_FINGERPRINT`. These names and the
  secret/variable split match Notoli/MacroMapper. Supply an independently verified
  `SHA256:...` server fingerprint. No separate known-host entry is configured.
- Use the dedicated `judeandrewalaba-infrastructure-actions` SSH key; retain its
  `restrict` options and separate identity from the app and desktop keys. The
  initial supported login is root. Upload private-key secrets as exact LF bytes;
  Windows text-mode pipes can introduce CRLF. The helper normalizes CRLF too.
- The transport discovers public host keys with bounded `ssh-keyscan`, verifies
  each locally against the configured fingerprint, then pins only the matching
  key and its negotiated algorithm before any SSH authentication or SCP upload.
  Unmatched/empty results fail closed. RSA keys use `rsa-sha2-512` signatures.
  Discovery never establishes trust by itself; strict host checking stays enabled.
- Repository secrets can be requested by other same-repository workflows; they
  do not provide an environment's branch-scoped credential boundary. Protect
  reviewed workflow/helper changes and repository write access accordingly.
  Only the gateway workflow references the key, only its transport step receives
  it, and its only triggers are `env-prod` push and owner manual dispatch on that
  branch. Review/scanner jobs must never request deployment credentials; keep
  the key outside Dependabot. Review these workflow rules explicitly; the root gateway regression suite has been retired.
  These controls prevent other existing jobs from initiating gateway operations;
  a writer able to install an arbitrary secret-reading workflow remains privileged.
  The helper's context checks cannot constrain a workflow that bypasses it.
- The Linux host needs Python 3.12+, Docker Compose, systemd and cached accepted
  Nginx images. Verify the deployment identity can run persistent systemd units.
  Origin TLS is always verified using the hostname/SNI. If using a private
  origin CA, provision its reviewed trust anchor at
  `/opt/host-ingress-deploy/origin-ca.pem`; public probes use system trust.

GitHub references: [Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
and [deployment concurrency](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments).

<a id="-private-host-preparation-and-adoption"></a>

### Private host preparation and adoption

Within the approved preparation plan, provision root-owned mode 0700
`/opt/host-ingress-deploy` and its `incoming`, `releases`, `attempts` children.
Use the **existing** root-owned 0700 `/var/lib/jude-deploy-locks` directory and
regular root-owned 0600 `maintenance.lock`. Never replace/unlink its inode;
the apps take it shared and this gateway transaction takes it exclusive,
nonblocking. Lock contention fails visibly rather than queueing inside the host.

Before the first automated release, obtain an exact, clean accepted gateway
checkout at `/opt/host-ingress`. Verify its source SHA against the running
gateway and the recorded acceptance evidence. If its certificate path differs
from the Compose default, supply the actual `INGRESS_CERTS_DIR` while adopting.
Run the reviewed helper from an operator-controlled checkout:

```sh
umask 077
python3 nginx/gateway_release.py adopt --source <accepted-full-sha> \
  --directory /opt/host-ingress
```

Adoption takes the exclusive lock, checks source cleanliness, topology, image,
mounts, listener/restart/logging policy and both public/origin health suites.
It captures an immutable private baseline and `current.json` without restarting
ingress. Existing app data and certificate/key files are neither copied into
the release bundle nor modified. Drift or an existing baseline blocks adoption;
resolve it privately, do not fabricate or edit release records to bypass checks.

<a id="-retired-mcp-routes"></a>

### Retired MCP routes

The [owner decision in #96](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/96) governs the removal. This
controller accepts the ordinary three-network gateway and can read the exact
previously accepted disabled tombstones for rollback. Enabled legacy profiles,
unmatched marker/vhost bytes and extra route networks are rejected. Contain
retired routes with their matched historical controller before using this source.
New source bundles contain no retired vhosts or profile selectors. Preserve
private accepted/recovery generations; historical controllers are evidence, not
authorization to reactivate retired services.

The read-only 2026-11-22 inventory found seven retained gateway generations with
retired route files, including three with both profiles disabled. Keep the exact
disabled-tombstone checks and rejection of enabled profiles while those recovery
generations remain. The live accepted gateway has both profiles at `base`.

## 🧭 Structure and ownership

[compose.yml](../compose.yml) owns project `host-ingress`, service `proxy`, container
`host-ingress-proxy`, runtime `/opt/host-ingress`. `gateway_release.py` owns authorized
transactions; `gateway_transport.py` verifies promotion before credential loading
and transports immutable inputs; `check_host.py` validates current host topology without repair. Its command is
`python3 nginx/check_host.py`; historical `legacy`/`vacant` handoff modes are
removed. Retained recovery generations keep their matched historical helpers.
App-only releases never shut down/reload ingress, alter certificates/shared networks,
use `down`/`--remove-orphans`, or prune the host. The independent website/apex route
is not transferred here. Inventory other hostnames before changing default rejection.

### Networks and proxy trust

Adopt existing network objects in place; inspect actual membership and IPAM rather
than assuming external Compose declarations verify them. Keep historical labels.

| Network | Permitted membership | Upstream / address contract |
| --- | --- | --- |
| `notoli_backend_private`, internal `172.30.88.0/29` | ingress + Notoli backend | ingress `172.30.88.2`, backend `172.30.88.3`, `notoli-backend:8000` |
| `notoli_default`, `172.18.0.0/16` | ingress + Notoli frontend | `notoli-frontend:80` |
| `macromapper-ingress`, `172.20.0.0/16` | ingress + MacroMapper frontend/backend | ingress `172.20.0.3`, `macromapper-frontend:80`, `macromapper-backend:8000` |
| `notoli_backend_egress`, `172.19.0.0/16` | Notoli backend only | app-owned outbound path |
| `macromapper_default`, `172.21.0.0/16` | MacroMapper frontend/backend | app-owned egress and frontend's generic `backend` alias |

Ingress joins only the first three. MacroMapper never joins Notoli networks;
Notoli frontend never joins its private backend network. Both apps have unpublished
backends and frontends. Shared ingress uses unique namespaced upstreams, never generic
`backend`/`frontend`. Keep app projects/container names and existing DB paths:
Notoli `/root/apps/notoli/db.sqlite3`, MacroMapper `/opt/apps/macromapper/db.sqlite3`.
No storage move accompanies ingress changes. Docker/root administrators remain privileged.

### Routing, TLS and privacy

Serve `notoli.judeandrewalaba.com` and `macromapper.judeandrewalaba.com` on 80/443
with HTTPS redirects, 25 MiB body limits and `/api`, `/auth`, `/admin` slash redirects.
Route `/api/`, `/auth/`, `/admin/`, `/static/admin/`, `/static/rest_framework/`, exact
`/mcp` and `/.well-known/*` directly to each app backend. `/` and SPA deep links,
including `/connections*`, go to its frontend. Preserve URI, query and encoded paths.
Docker DNS uses `127.0.0.11`, `valid=10s`, `ipv6=off`, variable upstreams and original
`$request_uri`; absent/recreated apps must not prevent startup or serving companions.

Overwrite Host and forwarded scheme/client with canonical Host, gateway scheme
and immediate `$remote_addr`; clear `Forwarded` and `X-Forwarded-Host`. Never trust
incoming chains. Notoli retains exact `DJANGO_TRUSTED_PROXY_IPS=172.30.88.2`, Uvicorn
`--no-proxy-headers`, exact-peer ASGI validation/stripping and Django's existing
forwarded-host/proto rejection. MacroMapper's app ASGI validates exact `172.20.0.3`
and strips untrusted forwarding headers. Do not copy Notoli's subnet or trust a CIDR.
Cloudflare visitor-IP restoration is outside this contract.

MacroMapper backend and MCP routes use a 120-second upstream idle read timeout,
allowing the app's 110-second total AI budget to return JSON before the proxy.
Confirm the effective CDN timeout independently. `/mcp` stays exact, HTTP/1.1,
empty Connection and buffering off; frontend upgrade behavior is separate. Verify
Nginx header inheritance in locations that add their own `proxy_set_header`.
Disable backend caching, hide upstream cache policy and return `no-store` for
private auth/API/admin/MCP and discovery, including failures. Keep query-free access
logs and disabled raw-request error logging so OAuth codes/state/tokens cannot leak.

The gateway owns HSTS `max-age=3600` on both HTTPS hosts, including private/error
locations; omit subdomain/preload directives. Keep explicit HTTP redirects. Django
W004/W008 must be assessed against real edge/origin behavior. Disabling HSTS requires
`max-age=0` over working HTTPS and expiry of the previous one-hour browser policy.

Certificates are host-owned and mounted read-only from the approved actual path
(default `/root/apps/notoli/certs`). App bundles never upload keys/vhosts or modify
that directory. Certificate relocation, rotation or rootless-user changes need
separate review. Keep private dirs/files 0700/0600 with runtime-compatible ownership;
never blindly change DB ownership. Preserve raw env-file bytes. No private keys,
environment values or full inspect/log output enters Git, comments or artifacts.
Full (strict) TLS, origin SANs/firewall, cache/WAF/challenges, actual key access and
SSH/GHCR capability require operator verification; HTTPS 200 alone proves none of them.
The accepted immutable image is selected by reviewed Compose and the host record;
historical cutover image digests remain recovery evidence only.

## 🌱 Application admission

Obtain owner architecture/admission approval after peak CPU/RAM, disk plus retained
images/backups and concurrent-release headroom review. Current checks do not certify
a third app. Assign independent project/data/env directories and a reviewed route
network with exact IPAM/membership/namespaced upstreams; keep unrelated DB/backend
networks off ingress. Network creation is an explicit operator action, never an app
release repair. Add reviewed DNS/SAN/vhost/edge policy with runtime DNS, safe headers,
encoded URI preservation, streaming/no-store/logging checks while the app is absent.

Adopt the [app-release contract](../app-release/README.md): immutable images, unique
private staging, protected maintenance/app locks, consistent SQLite capture, matched
config/env/images, bounded readiness and explicit data rollback. Capture backup
destination/retention/restore owner, bounded logs, alerts/response ownership and
capacity upgrade triggers. Proposed operational baseline is daily encrypted off-host
backup with 7 daily + 4 weekly retained; destination/credentials/spend remain unapproved
until selected. Source PR approval is separate from each merge and command-level
activation approval. Prove independent redeploy/recovery without changing companions.

## 🔌 Optional MCP contract

Each app advertises MCP only after its own reviewed ASGI lifecycle, registry/scopes,
OAuth migrations/client policy, exact proxy trust and readiness pass. Infrastructure
creates no accounts, grants, business tools or shared issuer. Each file under
`vhosts/` shows its MCP, discovery and private-cache rules directly. Only TLS and
forwarded-header settings use direct includes; neither includes another file.
`/auth/mcp/authorize/`, `/token/`, `/revoke/` and `/connections/` stay within private
`/auth/`; browser `/connections` and `/connections/authorize` remain frontend pages.
JSON Streamable HTTP needs no WebSocket route. Bounds/lifespan/session handling are
app-owned. Use exact HTTPS public-client callbacks, S256 PKCE, no password/implicit
grants or dynamic registration. Tools enforce live ownership/membership per call.
Review MCP/discovery edge rules: no interactive challenge, caching or path rewriting.

Enabled readiness adds exact issuer/resource metadata and `/mcp` 401 with the
resource-metadata Bearer challenge to normal frontend HTML/API JSON checks. Ordinary
profiles must not advertise metadata/challenges; SPA HTML is not discovery. Notoli
and MacroMapper own their profiles; template onboarding is no third deployment.

### MacroMapper activation order

For initial adoption, review both sources and app assertions, then release reviewed
gateway routing first. Confirm the old backend returns unimplemented-path 404 for
MCP/discovery (uncached, never SPA HTML/another issuer). Verify ordinary routes and
unchanged app/network/certificate identity. Independently release the app ASGI/OAuth
implementation through its matched SQLite/recovery transaction; required metadata
checks otherwise fail behind an old gateway. Verify public/origin metadata, exact
resource audience/challenge, both approved PKCE clients and existing Notoli behavior.
Routing stubs do not prove authenticated tools or isolation. Recover failed app
acceptance with the app's matched release; gateway can keep forwarding old 404s.
Gateway rollback does not reverse OAuth migrations or revoke grants. Do not revoke
the owner's existing connection merely to test revocation. Record scope/outcomes on #4.

### Inactive onboarding example

Use an existing file under `vhosts/` as a starting point. Review the app's
upstreams, route networks, exact proxy trust, certificate and readiness policy
before adding a vhost. This guide enables no new service.

## 🧪 Checks and acceptance

The gateway integration test uses `python3 nginx/gateway_release.py check-config --directory . --certificates <directory>` to verify a rendered Compose model supplied on standard input. `--record <file>` checks recovery state and `--syntax` runs the pinned image’s nginx syntax check in an isolated container.


See [workflow checks](../.github/workflows/README.md#-checks-and-diagnostics).
Compose configuration, shared release manifest and action-local regressions remain;
root routing, gateway transaction/retirement, snapshot and profile tests were retired.
No current local result substitutes for live topology, handoff/recovery or authenticated
acceptance. Use disposable networks/test certificates for rehearsals. Never run the
production cutover as a test. Unauthenticated public readiness is separate from account,
email and billable-AI operations, each requiring its authorized scope.
