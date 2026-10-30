# 📦 Independent YNAB release contract

This #61 source is an **owner-operated candidate**, not production authorization.
Every final artifact must pass the [full-image gate](ynab-artifact-security.md).
No automatic deployment trigger, registry publication, host provisioning,
credentials, network creation or ingress promotion is added. Pass the artifact,
capacity, gateway-profile and #62 operator/client gates before any live command.

## 🧩 Reuse and ownership

`scripts/ynab_release.py` reuses `gateway_release.py`'s private-file checks,
durable atomic records/fsync, Docker invocation/diagnostics, stable-inode locks,
companion inventory and certificate identity. The host maintenance lock remains
exclusive for gateway releases; YNAB takes it shared plus its own exclusive
`ynab-mcp.lock`, following the existing app lock order. Existing gateway behavior
and `app-release/v1` consumers remain unchanged.

The v1 application transaction requires Django backend/frontend management and
an existing SQLite database at import. YNAB owns two stateless process services
and no database/migration. Its app policy uses the existing host primitives with
its own small journal, rather than supplying a fake Django/SQLite application or
copying the v1 engine. It never executes database recovery, another application's
Compose file, Nginx reload/recreation, `down`, orphan removal, pruning or network
provisioning. Monitoring/backup automation remains Infrastructure #24's scope.

## 🗂️ Private source and records

After separate host-setup authorization, the designated Linux operator prepares
root-owned mode-0700 `/opt/ynab-mcp-deploy` and its `releases`, `records`, `attempts`
directories. Prepare the existing shared lock directory and root-owned mode-0600
`maintenance.lock`/`ynab-mcp.lock` once; never replace their inodes during a run.
The controller requires the authorized root operator, a local Unix Docker socket
and a persistent systemd invocation. These are operational checks, not an
adversarial boundary against an administrator or arbitrary workflow writer.

Use a clean checkout at the exact reviewed source SHA. The controller reads the
canonical app-only Compose/overlay/ACL with `git show`, resolves only image/path
inputs, and stages mode-0600 config plus matched copies of the existing protected
token, identity and issuer public-key files. Files remain uid/gid 65532, mode0400,
inside private directories. Secrets never enter Compose environment values,
arguments, public diagnostics or Git. Staging/provisioning credentials still
needs the separate owner authorization required by #62.

`records/<source>-<uuid>.json` tracks exact images, configuration/secret hashes and
runtime identity. `current.json` identifies accepted state. `pending.json` is the
durable mutation barrier; `attempts/<uuid>.json` retains success/recovery evidence.
Diagnostics use the existing private bounded command-output records. Runtime logs
and proxy cache are disabled; inherited Squid log/spool paths are explicit bounded
tmpfs mounts, so anonymous persistent image volumes are not created.

Keep all these records private. Retain previous images and matched files for
rollback. Review disk usage and archive completed diagnostics/old generations
under the existing operator retention/backup process; never delete a pending,
current or referenced recovery generation. No cleanup daemon or timer is added.

## 🚦 Stage, promote and recover

Every **stage**, **deploy**, **promote** and active-image **rollback/recovery** runs
the paired exact-image preflight afresh under the locks. No saved approval JSON
or passing egress scan can replace the gateway scan. Stopping a failed initial
activation remains possible even if its artifacts are now rejected.
`rollback` always selects an active previous generation and scans both images
before restarting it. If no such generation exists, use the separate `disable`
operation to stop services. Pending initial-failure recovery requires the explicit
`--stop-only` flag. These containment paths only stop owned services, never start
an image, and remain available when scanning is unavailable or an artifact is rejected.

The operator invokes the reviewed controller in a persistent `systemd-run` unit,
with UMask0077, a finite deadline and reviewed memory/CPU/PID limits. Reserve
capacity for the scanner and temporary image/filesystem exports **before** this
operation. The production VM's spare capacity is unverified; local fixture
success does not establish it. A unit or scanner resource failure blocks release.
Do not run the current scan-heavy preflight on a constrained live host without
the separate capacity review. Resource-limit and disk-headroom decisions belong
in the exact #62 plan, not an inferred approval from the advertised droplet size.

The CLI supports these operations (paths/images below are deliberate placeholders):

```sh
# Inside the separately authorized persistent unit, from the reviewed checkout:
python3 scripts/ynab_release.py stage --source REVIEWED_40_HEX_SHA \
  --gateway IMMUTABLE_GATEWAY_REFERENCE --egress IMMUTABLE_EGRESS_REFERENCE \
  --secrets /private/provisioned-files --scanner /private/trivy --cache /private/audit-cache

python3 scripts/ynab_release.py promote --id STAGED_SOURCE_UUID --initial \
  --scanner /private/trivy --cache /private/audit-cache

python3 scripts/ynab_release.py recover --confirm-stopped-attempt \
  --scanner /private/trivy --cache /private/audit-cache

# Pending initial activation with no active previous generation:
python3 scripts/ynab_release.py recover --confirm-stopped-attempt --stop-only \
  --scanner /private/trivy --cache /private/audit-cache

# Stop an accepted generation without starting any image:
python3 scripts/ynab_release.py disable --confirm-stopped-attempt \
  --scanner /private/trivy --cache /private/audit-cache
```

`stage` produces an inactive private candidate for operator inspection. `promote`
rechecks both exact artifacts, verifies matched files and only then runs app-only
`up --no-deps --pull never egress gateway`. `--initial` is required when no accepted
state exists; existing untracked containers are rejected. `deploy` combines stage
and promotion for a separately approved later update. `rollback` explicitly
selects the accepted previous generation, with new scans; it does not require
reconstructing old configuration from current environment variables.

Private loopback live/ready probes and an internal CONNECT listener check bound
startup. They make no financial API request and do not validate the real token's
YNAB authorization. Both services use the existing hardening/resource/no-restart
profile; app/container/endpoint ownership and unchanged companion/network/cert
identities are checked before acceptance. No caller replays a financial request.
The exact network gateways and required service DNS aliases are checked. Extra
capabilities and security-option relaxations are rejected. Accepted gateway
profile/runtime evidence determines whether ingress must already be attached:
the app may be privately ready under the disabled tombstone before first exposure,
but an enabled profile cannot silently lose its ingress endpoint. Private app
readiness does not establish public routing or either client's acceptance.
Every update/restart invalidates in-memory sessions; clients must initialize anew.

A failed, timed-out or killed mutation leaves the barrier. Do not retry or delete
it. Inspect the prior persistent unit and Docker daemon outcome privately before
using `--confirm-stopped-attempt`; the flag records an explicit operator recovery
choice and never bypasses artifact/ownership checks. Recovery restores the exact
previous matched image/config/files, or stops the two app services after a failed
first activation. Rejected old artifacts block restart and require a new reviewed
fix; there is no silent advisory waiver. Gateway route disablement is a separate
gateway-only release, using the reviewed 410 profile.

## 🧪 Disposable acceptance

```sh
python -m unittest discover -s tests -p test_ynab_release.py -v
python -m unittest discover -s tests -p test_ynab_release_docker.py -v
```

The state suite covers scan-before-mutation, inactive staging/re-scan on promotion,
matched rollback, corruption, newly failing old scans, initial disable/redeploy,
restart barriers and shared/exclusive locks. The Linux Docker fixture uses a
unique project and three internal networks, synthetic HTTP/socket providers and
actual journal/ownership/Compose operations. It upgrades, rejects incompatible
startup, rolls back, then SIGKILLs the controller after a completed Compose switch.
A new controller must refuse another deploy and explicitly recover. Companion
container, SQLite bytes, certificate markers and network IDs stay unchanged.
The actual gateway/stdio/TLS/secret policy remains covered by its separate image
runner; these fixtures never claim real-client or production acceptance.
