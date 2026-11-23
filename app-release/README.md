# 📦 Shared application release standard

FullStackTemplate, Notoli and MacroMapper use the same versioned release implementation in
[`v1/`](v1/). Each application vendors an exact copy of
the release/bundle tools and five test modules. The builder also verifies shared
parity; `shared_source` in `deploy/production/app.json` selects a full
Infrastructure commit SHA. This is a
build-time dependency: the private release bundle contains the runtime script,
`app.json`, Compose and environment files needed for offline recovery.

## 💻 Application local file names

Application repositories use these independent local inputs under `deploy/`:

| File | Purpose |
| --- | --- |
| `compose.yml` | Built application images behind a local HTTPS proxy |
| `compose.hotswap.yml` | Mounted source with automatic backend/frontend reload |
| `.env.example` | Committed local settings example; copy to private `.env` |
| `nginx.conf` | HTTPS proxy configuration mounted by local `compose.yml` |

Production remains `deploy/production/compose.yml`, using the existing shared
gateway and private `.backend.env` release bundle. Retained historical archives
can still contain `docker-compose.yml` and `nginx-proxy.conf`; those files belong
to their historical procedures. New recovery captures keep effective runtime,
the matched previous release and SQLite data, without recopying root-stack files.
The local renames require no shared-source pin, manifest or host changes.

The naming rollout covers FullStackTemplate, MacroMapper and Notoli. Infrastructure
already uses root `compose.yml`; its adoption is documentation only. See each
application's `deploy/README.md` for the updated local commands.

## 🧭 Contract and ownership

`deploy/production/app.json` contains the app name, service/container names,
domain, database paths, environment requirements/defaults/fixed values, network
membership/address/port policy, readiness probes and workflow-specific inputs.
`compose.yml` remains the readable app-specific service definition. There are no
application-name branches in the common production scripts.

The common transaction owns validation, immutable image selection, private
staging, maintenance/app locks, runtime capture, SQLite journal/generation
handling, migration/startup, bounded readiness, failure barriers, explicit
restore/keep recovery and success records. Docker logs retain the same 10 MiB × 3
cap; recovery artifacts and old images remain private until operator-reviewed
retention cleanup. It never operates another app or the shared gateway.

Public readiness requests identify the deployment client as `JudeAppRelease/1.0`
and request uncached responses. This avoids generic Python-client signature
blocks without impersonating a browser or weakening edge security. Expected
status, content and authentication challenges remain mandatory.

The transaction writes plain progress steps to stderr. Errors name the current
step, failed commands include their exit code, and readiness timeouts distinguish
the direct backend API from public routes. Captured command output, environment
values and parsed exception values remain private. Failure messages point to the
app's `FAILED.json` if present and `recovery/`; an early failure may precede a
complete recovery set. A disconnected progress stream does not interrupt the
transaction, and acceptance is announced only after readiness and success records.

Each app policy describes only its own route networks in detail. Its optional
`gateway.allowed_networks` lists all approved gateway attachments; without it,
only the app's route networks are allowed. App routes remain required and unknown
attachments fail, while approved companion routes may be absent. Unexpected members,
address/trust drift and published ports still fail. Infrastructure's `nginx/check_host.py`
retains the full-host topology audit and both-app gateway cutover acceptance.

Preflight verifies running frontend bindings against the accepted release's
checksummed app policy. The incoming bundle's own policy is checked against
rendered Compose before staging images and against Docker after recreation,
before recording success. This allows a reviewed port change while still
rejecting drift. Recovered releases require their checksummed saved app policy;
missing policy never falls back to the incoming candidate's port defaults.
Notoli and MacroMapper use shared HTTPS ingress and have no
host frontend publication. See [Infrastructure #23](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/23)
for Notoli's consumer inventory and rollout evidence.

The transaction stays in one file because its ordering and crash barriers form
one recovery state machine. Separating app policy and readiness predicates removes
unreachable code without scattering that state machine across artificial layers.

The rollback CLI selects the checksummed `release.py` and `app.json` from the
chosen recovery set's `previous-release/` directory and runs that controller's
rollback under the existing maintenance/app locks. It never re-enters another
CLI or reacquires the locks. The recovery ID and restore/keep-data choice remain
explicit; readiness comes from the saved policy, including disabled MCP profiles.
Selection is offline and rejects incomplete, altered, foreign or unrecorded saved
controllers before mutation. Capture also checks a recorded controller before
stopping writers or migrating. After a recovered runtime is redeployed, its
original controller/policy is preserved again rather than lost from the next
recovery set. Legacy/unrecorded recovery and older tools retain their separately
reviewed manual procedures; immutable bundles are never rewritten.

## 🔀 Intentional application differences

| Contract input | Notoli | MacroMapper |
| --- | --- | --- |
| App root | `/root/apps/notoli` | `/opt/apps/macromapper` |
| Services | `backend`, `frontend` | `macromapper-backend`, `macromapper-frontend` |
| Backend networks | private `/29` + separate egress | app ingress + app default/egress |
| Frontend networks | `notoli_default` | app ingress + app default |
| Trust/address | exact proxy `.2`, backend `.3`; Uvicorn peer handling preserved | canonical forwarded HTTPS behind restricted backend reachability |
| Published frontend port | none | none |
| Common readiness | direct API 401, public HTML 200 and JSON API 401 | same |
| Extra readiness | OAuth issuer/resource metadata and MCP challenge | Same for the app-owned MCP release; functional AI/mail checks remain separately authorized |
| Extra environment | MCP origin and trusted proxy | OpenAI key, model and timeout; app-owned MCP origin and exact `172.20.0.3` trust |
| Frontend build argument | `VITE_API_BASE_URL=` | `VITE_API_BASE_URL=` |

## 🔒 Automated parity and updates

App CI's existing automation test gate runs `python3 deploy/production/build_bundle.py --check-parity`.
The builder’s explicit `--check-parity` mode fetches the manifest and workflow template at the pinned commit,
then compares common source/test hashes and the rendered workflow.
Unintended code, test or workflow changes fail CI. Windows CRLF is normalized;
other byte differences are rejected. Source retrieval failure also fails the gate.
Backend and frontend builds keep `./backend` and `./frontend` as their contexts
and select `./backend/docker/Dockerfile` and `./frontend/docker/Dockerfile`
explicitly; Nginx configuration stays under the frontend Docker folder. All external production action references are pinned. The deployment build checks
parity again before accessing destination credentials or publishing images.

For a coordinated update:

The current template pins `docker/login-action` v4.8.0. Dependabot login-action
updates in application workflows must adopt the shared template commit through
the procedure below; changing only the rendered workflow fails parity.

1. Edit common source/tests/template here and run
   `uv run --locked python app-release/update_release_manifest.py`. Infrastructure CI verifies the
   manifest with `--check`.
2. Commit and review the shared changes. In all three app PRs, set the same immutable
   commit in `shared_source` within `deploy/production/app.json`, then run
   `uv run --locked --project backend python deploy/production/build_bundle.py --check-parity --sync`. It copies the approved common files
   and renders the workflow using that app's configuration.
3. Run parity and the full deployment tests in each app. Review configuration or
   Compose differences explicitly; never edit only one vendored engine.

During local development, `--source-root <infrastructure-checkout>` performs the
same checks without network access. CI never uses this override. Bundle creation
and retained host recovery never fetch shared source. Use `--sync` only with
`--check-parity`; it validates all source downloads before replacing local files.
Synchronization replaces only common files and the rendered workflow; unrelated
local files remain untouched. A linked `deploy/` directory is rejected before
writes. The completed parity-checker cleanup migration is no longer run.
All frontend builds use `VITE_API_BASE_URL=`; app-specific Actions settings remain
in `workflow.extra_env`. The unused `root_hint` is omitted; `DEPLOY_PATH` supplies
the actual destination. A version bump
is required for incompatible contract semantics; coordinate adoption in all three app
PRs. Explicit pin changes are reviewable upgrades, not an automatic deployment.

The November 14 unused-code audit removed the bundle builder's unused origin
constant after checking workflow entry points and all three consumer suites.
Runtime readiness retains its separate origin value. SQLite backup progress
callbacks keep their three-argument signature, and historical-generation guards
remain necessary for recovery. This cleanup does not authorize production work.

## 🧪 Verification and operations

Both apps execute the same fault, SQLite/WAL, generation/checkpoint, timeout,
lock, readiness, missing-backend and retry tests. App-policy regressions retain
Notoli's exact trust/MCP behavior and MacroMapper's unpublished frontend/OpenAI
requirements. Real Docker recovery checks preserve companion container identity,
configuration, database bytes and a separate gateway fixture. Infrastructure's
root Nginx route/handoff/reversal suite has been retired; current CI does not
establish gateway runtime acceptance.

Each app keeps one canonical `deploy/production/README.md`; local Docker setup
lives in `deploy/README.md`. Architecture/merge/production approvals and rollout
status stay in [coordination issue #4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4).
The approved order remains gateway acceptance → Notoli → MacroMapper, each with
separate authorization and repeat-release/recovery verification.

## 🧩 Template adoption

FullStackTemplate may vendor this standard using its own app policy, without
inheriting Notoli's MCP/proxy trust or MacroMapper's OpenAI requirements. Common
contract/preflight regressions derive fixtures from the selected policy; explicit
checks still preserve the two existing applications' trust and secret boundaries.
The former root release-profile matrix and its fixtures have been retired.
Canonical `app-release/v1/tests/` remains unchanged and consumers execute their
vendored suites against their own app policies. MacroMapper's policy enables
app-owned MCP with exact `172.20.0.3` trust and origin/challenge readiness; the
ordinary template retains the disabled MCP contract. Consumers pin the same
reviewed Infrastructure source commit before synchronizing their vendored copies.

The template profile is an onboarding example, not a third application approved
for the shared host. It does not add gateway routes, networks, certificates,
capacity, or deployment authorization. An operator must review the actual full
gateway topology, chosen subnet, bootstrap, locks, and capacity before activation.
All consumers must pin the same reviewed source commit when adopting this change.


## 🔌 Optional MCP applications

Follow the [gateway MCP contract](../nginx/README.md#-optional-mcp-contract). Apps own
ASGI/OAuth, readiness and rollback; keep independent releases and exact proxy trust.
The shared contract suite models immutable Action upgrades: isolated consumer edits
fail parity; approved source synchronization passes; unrelated drift remains rejected.

### Email backend selection

Application configuration lives in `backend/config/` and domain modules in
`backend/apps/`. Set `DJANGO_EMAIL_BACKEND` explicitly to
`anymail.backends.resend.EmailBackend` for Resend API delivery or
`django.core.mail.backends.smtp.EmailBackend` for SMTP. New bundles reject retired
custom-backend names and other unsupported selectors before creating output.
Django settings preserve the configured backend name without translating it.

The Actions variable update changes the next bundle's input; it does not deploy
or edit live processes, private recovery bundles or their saved environment.
Retained bundles use their matched images/controllers. Each app owns its
Anymail credential/timeout configuration and mocked auth/privacy acceptance.
