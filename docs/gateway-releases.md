# 🚦 Subsequent gateway releases

This is the release procedure for the already adopted `host-ingress` gateway,
not the [one-time cutover](cutover.md). The owner's October 19 policy makes an
authorized promotion of reviewed source to `env-prod` the release authorization:
it automatically deploys without another human reviewer or per-release approval
variable. Source/CI approval alone still does not authorize branch promotion.
GitHub's original actor and retrying actor must both be the repository owner;
another collaborator or bot cannot authorize a production operation.
Record initial setup, the designated operator, rollout/recovery scope and results
on [coordination #4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4).
Independent Notoli/MacroMapper workflows and shared release code are unchanged.

The current source candidate pins the official Nginx **1.31.8 Alpine 3.24 slim**
Linux/amd64 image at
`nginx@sha256:f9238a4aacf18df0f059cf0389490fc2e876352f75d019f475a48e8765576f24`.
Its complete native-package assessment and existing TLS, proxy, gzip, DNS, MCP
streaming and recovery fixtures must pass before source promotion. This replaces
the blocked Debian candidate without changing the Nginx release version. Historical
image references in the one-time cutover guide remain matched recovery evidence;
they are not an approval to deploy an image with unresolved advisories.

## 🔒 Approval and prerequisites

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
[shared policy](https://github.com/VanillaIceCube/FullStackTemplate/blob/main/docs/SHARED-ROLLOUT-POLICY.md#main-first-releases)
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
  the key outside Dependabot. Regression checks enforce these workflow rules.
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

## 🔄 Migrating existing Actions settings

1. Inventory `production`, `gateway-approval` and `gateway-production` secrets,
   variables and consumers. Keep the old settings until the new path is verified.
2. Securely re-enter the original dedicated key as repository Actions secret
   `DEPLOY_SSH_KEY`; GitHub cannot reveal an existing secret. Reuse the verified
   key when available; rotation changes host access and needs explicit scope.
   Copy the four connection variables to repository Actions variables. Preserve
   `DEPLOY_ENABLED`; do not copy deployment credentials into Dependabot.
3. Merge reviewed source to `main`, then make the owner-authorized `env-prod`
   promotion. Verify the exact Actions run/attempt, sanitized summary and durable
   host result, including the actual running source for an unchanged gateway.
   Confirm host health, preserved app/network/certificate identities and locks.
4. Only after acceptance, delete the obsolete `production`, `gateway-approval`
   and `gateway-production` environments and their scoped settings. Check for
   active jobs and any unrelated consumers first. Deletion removes environment
   secrets and protection rules and fails jobs waiting on those rules; retain
   sanitized Actions evidence before cleanup. See [environment deletion effects](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments#deleting-an-environment).
   Historical deployment records can still reference the old environment names;
   retain their run links, but do not use them as the current release authority. The new
   workflow creates neither environment jobs nor Deployment API records, so it
   cannot recreate these environments. The concurrency group name is only a lock.

To reverse source before cleanup, retain the old environment credentials and
use the normal reviewed promotion process. After cleanup, reverting to the old
workflow also requires securely reprovisioning its environment settings. This
settings migration does not authorize a gateway configuration rollback or app release.

## 📦 Private host preparation and adoption

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
python3 scripts/gateway_release.py adopt --source <accepted-full-sha> \
  --directory /opt/host-ingress
```

Adoption takes the exclusive lock, checks source cleanliness, topology, image,
mounts, listener/restart/logging policy and both public/origin health suites.
It captures an immutable private baseline and `current.json` without restarting
ingress. Existing app data and certificate/key files are neither copied into
the release bundle nor modified. Drift or an existing baseline blocks adoption;
resolve it privately, do not fabricate or edit release records to bypass checks.

## 🚀 Promotion and retry

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

## 🩺 Health and relevant changes

Both the public edge and loopback origin verify HTTPS frontend HTML, JSON API
401 responses for both apps, Notoli issuer/resource discovery and the MCP 401
authentication challenge. Origin connections preserve hostname verification
and SNI with a separately provisioned CA if necessary. Redirects/challenges
cannot silently pass. Requests use `JudeGatewayRelease/1.0` and cache bypass
headers. Each complete suite has an 80-second process deadline, three attempts
and two-second intervals (244 seconds maximum); each socket has a five-second
timeout and responses are limited to 256 KiB. Real ingress route/DNS tests also
cover the existing 120-second backend/MCP timeout contract.

Restart policy compares the effective expanded Compose model, immutable image,
all `nginx/**/*.conf` bytes and certificate mount location to the **actually
accepted host record**, not the previous Git push. It normalizes release-directory
paths. Changes only to docs, workflow/helpers or `app-release/v1` produce an
`unchanged` attempt after baseline health checks; the gateway ID and running
source stay unchanged. Compose/Nginx byte changes restart after validation.
Unsupported payload files and Compose settings fail explicitly.

## ↩️ Failure, interruption and explicit rollback

Before activation, `attempts/<identity>/journal.json` captures the previous
matched configuration/image/source/runtime, application identities, network IDs,
certificate identities and Actions run. `pending.json` is fsynced before any
activation. Pre-activation rejection leaves the accepted runtime unchanged.
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
python3 scripts/gateway_release.py rollback --source <approved-helper-full-sha> \
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

## 🧾 Evidence and retention

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

## 🚦 Optional YNAB route

The [profile contract](gateway-profiles.md) adds a permanent validated selection
to this same bundle, transaction and owner-promotion path. The default stays
`base`; first use requires the disabled tombstone baseline, and subsequent
gateway releases preserve the accepted optional network/profile. No production
variable, app service or provider setting is activated by merging this source.
