# 📦 MCP issuer releases and recovery

The issuer is one stateless container around a separately persistent SQLite
directory. `scripts/mcp_auth_release.py` reuses the existing private-file, fsync,
maintenance-lock, Docker and canonical SQLite snapshot primitives. It does not
modify shared `app-release/v1`, other apps, ingress, networks or certificates.
Source review and local fixtures do not constitute production acceptance.

## 🔒 Prerequisites and ownership

Use an exact reviewed, clean Infrastructure checkout and a role-specific immutable
image reference: `ghcr.io/vanillaicecube/judeandrewalabainfrastructure-mcp-auth@sha256:…`.
The operator provisions `/opt/mcp-auth-deploy` mode0700, its private releases,
records, attempts/recovery/diagnostics, and `data` owned65532:65532 mode0700.
Keep both keys in protected files named `django_secret_key` and `signing_key.pem`;
staged runtime copies are service-owned mode0400. Protect journals alongside the
database. Do not bind only `db.sqlite3` or supply an existing corrupt database as
an apparently empty first deployment.

Use the existing protected, stable `maintenance.lock` and a separate mode0600
`mcp-auth.lock`. The controller takes shared maintenance then exclusive app lock
for staging, scanning, migrations and recovery. Run it in the separately
authorized persistent systemd unit with umask0077 and finite resource/deadline
bounds. Source/image pins and private matched files cannot be replaced by a
saved approval JSON. No ambiguous Docker mutation is retried.

Provision the existing-host route network separately through the reviewed operator
plan. The controller only validates its exact identity/IPAM/member contract.
Before every migration or restore, accept both auth and YNAB **disabled** ingress
tombstones. The mandatory [containment helper](mcp-auth-ingress.md) verifies the
accepted mounted/runtime state and actual origin HTTPS410 using the existing CA.
No boolean flag or unverified TLS probe substitutes for containment.

Reserve capacity for image exports, the pinned scanner and the running apps.
Measure available memory/disk at each stage; maintain the repository's512MiB
representative-load memory floor. Local synthetic peaks inform the operating
budget but do not prove live capacity. Scan and start stages run sequentially;
resource failure blocks the release, without a silent advisory or capacity waiver.

## 🚀 Stage and promote

These are interface examples; private paths, digests, operator and exact effects
belong in the reviewed #56 plan and KnowledgeVault, not copied from placeholders.

```sh
python3 scripts/mcp_auth_release.py stage --source REVIEWED_40_HEX_SHA \
  --image IMMUTABLE_AUTH_REFERENCE --key-id REVIEWED_KEY_ID \
  --secrets /private/provisioned-auth-files \
  --scanner /private/pinned-trivy --cache /private/audit-cache

python3 scripts/mcp_auth_release.py promote --id STAGED_SOURCE_UUID --initial \
  --scanner /private/pinned-trivy --cache /private/audit-cache
```

`stage` is inactive. Promotion revalidates exact files/model/image, both contained
routes, unchanged companions/network/certificates and a fresh full-image scan.
It records the pending barrier before stopping writers, captures the complete
SQLite main/WAL/rollback-journal namespace, and validates a canonical isolated
snapshot. Management containers are recorded before start and restricted to the
matched image/files. Migrations, deployment checks and migration-drift checks
precede starting only `authorization` with no dependencies or pulls.

Django deployment checks use its `ERROR` threshold. Expected warnings remain
visible in private management evidence: DOTW008 concerns the permitted literal
RFC8252 loopback callbacks (the registration validator rejects other HTTP hosts),
while securityW005/W021 concern optional HSTS subdomain/preload choices. No check
is globally silenced. Missing keys, unsafe runtime settings, dependency findings
and malformed callback/resource policy remain blocking failures.

Private process/database readiness does not prove owner/client registration or
real OAuth acceptance. A migrated empty user table passes readiness: the probe
executes a schema query without requiring a row. This lets initial promotion
complete under disabled routes before closed bootstrap. Closed bootstrap and fixed-client registration use the
[service management interfaces](../services/mcp-auth/README.md) in the separately
reviewed operator sequence while routes remain contained and app locks are held.
Protect transient password/credential inputs and record ambiguous command outcomes;
never replay an uncertain account or grant mutation. Register actual ChatGPT/Codex
callbacks and explicit existing-user links before exposing consumer endpoints.

## 🛟 Explicit recovery

```sh
python3 scripts/mcp_auth_release.py recover --strategy restore \
  --confirm-stopped-attempt \
  --scanner /private/pinned-trivy --cache /private/audit-cache
```

A failed, killed or timed-out operation retains its barrier and matched records.
First inspect the prior unit and daemon to establish that no mutation remains
active. Recovery checks every writer sharing the protected data directory,
including resolved bind aliases. It retains failed-writer journals before changing
data and never substitutes an image rollback for a changed schema.

`keep` is allowed only before migrations began. Otherwise explicit `restore`
retains the entire old directory and switches a separately prepared, verified
directory. Durable directory identities allow recovery after death between either
rename and its journal acknowledgement. Do not delete temporary/retired namespaces
or hand-copy main database bytes over journals.

Before restoring bytes, extend the private durable YNAB JWT quarantine by at least
905seconds. Revoke restored access/refresh grants, authorization codes and Django
sessions, independently verify the pinned tables are empty, then validate/start
the matched previous generation. Existing clients must authorize again. YNAB
ingress cannot re-enable until quarantine expires and the auth barrier is clear;
offline JWT signature validation alone cannot observe central revocation.

A failed first activation remains stopped with its database and evidence retained.
The controller never erases it to manufacture a clean initial deployment. Retain
current/referenced images, files, snapshots and keys under the existing protected
backup/retention process. Include the full data namespace and matched key files in
off-host recovery scope; no new backup service or automatic cleanup is introduced.

Key rotation additionally requires a matched YNAB offline public-key update while
both routes are contained. Recheck issuer/client/user identity and both clients
before re-exposure. Never shorten quarantine or replay stored approval evidence
as a key-rotation shortcut.

## 🧪 Validation

Run `test_mcp_auth_release.py`, `test_mcp_auth_release_docker.py`, containment and
artifact-preflight suites on a disposable Linux/CI daemon. The real Docker fixture
covers initial activation, upgrades, migration failure, matched rollback, grant
invalidation, interrupted directory replacement and SIGKILL with unchanged
companions/network identities. Its scanner, issuer and financial inputs are
synthetic; it never authorizes live activation or YNAB writes.
