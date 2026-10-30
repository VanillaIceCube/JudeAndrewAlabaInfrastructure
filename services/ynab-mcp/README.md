# 🧾 Isolated YNAB stdio runtime

Source implementation for [#58](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/58).
**Inactive and network-disabled. No production artifact is approved or published.**
The [gateway decision](../../docs/ynab-mcp.md) and #59–#62 still gate remote
authentication, controlled egress, release/security acceptance and activation.

## 📌 Source and artifact integrity

[`upstream.json`](upstream.json) is the canonical Oliver 6.1.0 source pin for
this runtime and the #57 experiment. The annotated tag object and peeled full
commit, raw LF lock hash and published-package SHA-256 are verified before a
build. All 49 published npm files must match their pinned Git blobs byte for
byte. Complete LF-normalized Dockerfile and policy-entrypoint hashes are pinned
as well; any recipe/policy change requires a reviewed pin update. The application
is neither forked nor vendored. Dependencies use its
unchanged lockfile with lifecycle scripts disabled; a high/critical npm audit
finding or unavailable audit fails the build.

The tag is unsigned and registry metadata exposes no attestation. These checks
establish content parity/integrity, not independently authenticated publisher
provenance. The current lock has two moderate affected packages associated with
the unused Hono HTTP adapter/static-serving path. A bounded stdio import check
loaded no Hono module; that is not an advisory waiver. Full image, license,
malware and signature evidence remains required before promotion under #61.
The separate Supergateway high/critical blocker is unchanged.

Both build and runtime bases are pinned to linux/amd64 manifest digests. The
shell-free, non-root runtime uses [Google's maintained Distroless Node 24 image](https://github.com/GoogleContainerTools/distroless/blob/main/nodejs/README.md).
Only upstream runtime code/dependencies and this repository's policy entrypoint
enter the final image; no npm, build tools, fixture tools, source checkout,
private environment or credentials are copied. The Docker build context is an
allowlist. No HTTP listener or production network exists in this stage.

## 🧪 Build and disposable acceptance

Use a disposable local/CI Docker daemon with BuildKit, Python 3.12+, Git and
outbound access to GitHub, npm and the pinned public image registries:

```sh
python services/ynab-mcp/build.py --tag ynab-mcp-runtime:review --record /tmp/ynab-build.json
python services/ynab-mcp/test_runtime.py
```

Builds bypass layer caching so advisory checks run again. The record refuses
overwrite and contains source/package/base hashes and the
**local image ID**, explicitly marked unpublished/unapproved. It is not a registry
manifest digest. #61 must record the real registry digest, full scanner evidence
and reviewed source before selecting a production image. A tag alone cannot be
promoted. No build command deploys, publishes, provisions a secret or changes a
Docker network. The tests remove only their uniquely named image/secret volume.

The existing validation job runs this suite under a five-minute bound. Real
upstream stdio initialization/discovery runs with a fixed synthetic token,
network disabled, root filesystem read-only, no published ports, uid 65532,
dropped capabilities and bounded CPU/RAM/PIDs. Tests check default financial-write
denial, explicit write-mode discovery, persistent journal retention across recreated
containers, and corrupt/unsafe journal rejection. Missing secrets/unsafe overrides fail closed, errors contain no
secret values, and app-only Compose has no shared mounts/networks/ports. No real
API request or financial mutation occurs.

## 🔐 Credential and runtime policy

The policy entrypoint requires `/run/secrets/ynab_api_token` to be a nonempty
regular file, 1–4096 bytes, uid 65532, mode **0400**, and not a symlink. The source
host directory must be protected (0700); Docker/root administrators remain
privileged. Compose file-backed secrets preserve the host file's ownership and
mode: `uid`/`mode` declarations are not a substitute for operator verification.
Never use an actual token in a build, CI, GitHub setting, issue, artifact or image.

The entrypoint refuses inline `YNAB_API_TOKEN`, 1Password lookup, autostart bypass
and agent-config fallback overrides. `YNAB_ALLOW_WRITES` accepts only explicit
`0` or `1` and defaults to `0`; write mode additionally requires `HOME=/data` and
the protected persistent journal directory. The gateway derives each child's mode
from its authorized session, never caller tool arguments. The entrypoint fixes
`YNAB_DISABLE_AGENT_CONFIG_FALLBACK=1` and removes `SENTRY_DSN`. Errors are generic;
Docker log storage is disabled. The future gateway must not log child stderr,
tool arguments/results, session/preview tokens or budget records.

Only the separately authorized operator may provision a real token. Validate
secret metadata and the immutable registry reference before any approved start:

```sh
python services/ynab-mcp/validate.py --image "${YNAB_RUNTIME_REPOSITORY}@sha256:${YNAB_RUNTIME_SHA256}" --token-file "$YNAB_TOKEN_FILE"
docker compose -p ynab-mcp -f services/ynab-mcp/compose.yml --profile manual-stdio config --quiet
```

These are preflight commands, not authorization to start the service. The
Compose image is constructed from a repository and mandatory digest component,
so a mutable tag cannot replace the digest when preflight is skipped. Secret
metadata and the exact 64-character lowercase digest are checked by `validate.py`;
Compose's own `config` command alone does not validate digest syntax. Invalid
digest syntax fails closed at Docker image resolution, without a tag fallback.
Secret
preflight also rejects symlinked paths, non-private parents and writable ancestors.
CI's external cleanup trap removes only the exact run's labeled containers,
image tag and synthetic-secret volume, including after a test timeout. Forced
host loss/SIGKILL still requires deliberate fixture cleanup; never prune globally.
The
`manual-stdio` profile cannot access any network, including YNAB; #59 must add a
separately reviewed, controlled egress arrangement. Do not bypass this by joining
Notoli/MacroMapper networks or publishing a host port. Limits are 256 MiB,
0.5 CPU, 32 PIDs and 16 MiB temporary storage pending measured #61 capacity review.

## 💾 State, rotation and recovery

The inactive standalone profile stays read-only with temporary HOME and no journal
mount. The owner-approved write-capable gateway profile uses unchanged upstream
file storage under `/data/.ynab-mcp-undo.json`. `/data` must be a regular directory
owned by uid/gid65532, mode0700; an existing journal must be a regular non-symlink
uid65532 file, mode0600, containing a JSON array. Corrupt/unreadable evidence is
never replaced with an empty journal. Upstream supplies atomic replacement, fsync,
cross-process locking, exact previews and durable multi-step recovery; no fork or
replacement protocol/journal engine is introduced. Treat journal contents and
unfinished operation records as private financial data under existing backup and
retention procedures. Keep the persistent namespace across code/image rollback;
restoring stale local history cannot undo external financial changes.

Rotation/revocation is private operator work: revoke the old YNAB credential,
prepare/validate the replacement outside CI, and recreate the affected runtime/
gateway under its app lock. Replacing a source file atomically does not update
an existing file bind mount; recreation is required and invalidates sessions and
previews. Keep prior verified image/configuration and private release records.
For a read-only runtime rollback, stop only the YNAB component, select the exact
prior digest/configuration, validate and reinitialize. Never restore financial
data, retry writes, run the host cutover, prune globally, delete shared networks,
or restart companion apps. #61 supplies the independent transaction; #62 supplies
the separately approved production operator plan.

Upgrades require a reviewed upstream tag/commit/package/lock and base-image pin
change, byte-parity/audit/container tests, the #57 session/preview proof, and
fresh image evidence. Never modify the upstream lock or silently override a
dependency to get a green scan. Image/standalone defaults remain read-only; public
write enablement additionally requires the gateway's explicit OAuth write grant
and existing preview/confirmation controls.
