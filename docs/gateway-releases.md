# 🚦 Subsequent gateway releases

This is the release procedure for the already adopted `host-ingress` gateway,
not the [one-time cutover](cutover.md). Implementation and CI do not authorize
environment setup, promotion, host preparation or production execution. Record
the designated operator, exact SHA, window, release/recovery scope and approval
on [coordination #4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4).
Independent Notoli/MacroMapper workflows and shared release code are unchanged.

## 🔒 Approval and prerequisites

Keep repository variable `GATEWAY_DEPLOY_ENABLED` unset until the operator plan
is approved. Setup is an explicit owner operation; this PR does not configure
live settings or credentials. Configure:

- Protect `main` and `env-prod`, require reviewed green PRs for source changes,
  and restrict `env-prod` promotion to the designated release operator. Promote
  an existing reviewed `main` commit, never an independent production commit.
- Environment **gateway-approval**: selected deployment branches, exactly
  `env-prod` (branch, no tags); required human reviewers; prevent self-review;
  disable administrator bypass. Name a reviewer other than the initiating
  operator. The workflow checks these settings through GitHub's API before SSH.
  Its token needs Actions read in addition to contents read/deployments write.
- Put `GATEWAY_APPROVED_SHA` in that environment, selecting the full, separately
  authorized `env-prod` SHA. Set repository `GATEWAY_DEPLOY_ENABLED=true` only
  after prerequisites and the initial baseline adoption below pass.
- Environment-only secrets: `GATEWAY_SSH_HOST`, `GATEWAY_SSH_USER`,
  `GATEWAY_SSH_PORT`, `GATEWAY_SSH_KEY`, `GATEWAY_SSH_KNOWN_HOST`,
  `GATEWAY_SSH_FINGERPRINT`. Use a dedicated production credential, not review
  credentials. The initial supported identity is root; a restricted alternative
  requires a separately reviewed privilege arrangement.
- Supply one independently verified OpenSSH known-host line, with host alias
  `gateway-host`, algorithm and public key. Supply its `SHA256:...` fingerprint
  separately. OpenSSH negotiates only that algorithm; `ssh-rsa` public keys use
  `rsa-sha2-512` signatures. No TOFU, keyscan acceptance or disabled host checking.
- The Linux host needs Python 3.12+, Docker Compose, systemd and cached accepted
  Nginx images. Verify the deployment identity can run persistent systemd units.
  Origin TLS is always verified using the hostname/SNI. If using a private
  origin CA, provision its reviewed trust anchor at
  `/opt/host-ingress-deploy/origin-ca.pem`; public probes use system trust.

GitHub references: [environment protection](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
and [deployment concurrency](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments).

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

After source review/green CI, record exact production authorization on #4,
set the environment's approved SHA, and promote that reviewed `main` commit
to `env-prod`. The push starts **Deploy gateway**, which waits for a different
required human reviewer. `main`/PRs never invoke deployment. Manual dispatch
must select **env-prod**, operation **deploy**, empty recovery field; it uses
the branch's exact current SHA, not a user-supplied revision. Each retry has a
new `<sha>-<run-id>-<attempt>` identity and requires a fresh approval.

Actions serializes runs with cancellation disabled. SSH uploads a bounded,
checksummed Git archive into private incoming storage. A persistent systemd
unit runs the transaction independently of the SSH session, with a 20-minute
outer deadline. Cancelling/losing the runner does not stop the host unit.
Do not cancel an active release as a recovery mechanism. Inspect its host
journal and systemd unit before another approved retry.

The exclusive lock covers topology validation, previous-state verification,
capacity, syntax checks, activation, bounded health, success recording and any
rollback. Capacity requires at least 512 MiB available memory and 20% free disk
(at least 1 GiB), rechecked after the immutable candidate image pull. This is a
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
succeeds. Failed recovery keeps the pending barrier and private evidence.

An interrupted mutation, including SIGKILL or host reboot, leaves the pending
barrier; a new deployment cannot bypass it. With separate recovery authorization,
dispatch **Deploy gateway** on **env-prod**, operation **rollback**, supplying
the exact failed/current release ID. The source approval still selects the
current env-prod helper; the recovery identity selects only retained host state.
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
gateway rollback; their current identities are captured under the lock.

## 🧾 Evidence and retention

**gateway-approval** is GitHub's automatic approval/job history.
**gateway-production** contains explicit pending/in-progress/success/failure
deployment records tied to the exact promoted SHA. A promotion that changes no
gateway configuration becomes `inactive`, with the actually running SHA in its
description; a retry of the already running exact SHA can be `success`.
A rollback attempt is `inactive` and names the restored SHA; a separate verified
recovery deployment selects the restored SHA and marks it successful. These operation
records never assert that a different attempted source is the running gateway.
Only verified success deactivates previous successful deployment records.

The durable host `current.json` is authoritative for the accepted running source,
image digest, configuration identity, Actions run and recovery reference.
Private attempt journals/results preserve promoted versus running identities.
Never publish full Docker inspect, journal/config contents, credentials or keys.
If a runner disappears, GitHub may show failure/in-progress while the independent
host unit completes: inspect systemd and `pending.json`/`current.json` privately,
then reconcile the deployment status for the **observed** running source under
the approved operator plan. A green job alone is not production acceptance.

Retain all incoming, release and attempt directories, previous images and
recovery records until operator-reviewed retention cleanup. No automatic
cleanup or off-host backup is included. Never remove a mounted/current release,
any pending attempt or its predecessor. Monitor disk space before future releases.
Production acceptance still requires the separately authorized first and second
independent release plus recovery evidence recorded on #4.
