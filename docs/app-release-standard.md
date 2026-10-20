# 📦 Shared application release standard

Notoli and MacroMapper use the same versioned release implementation in
[`app-release/v1`](../app-release/v1). Each application vendors an exact copy of
the release/bundle tools, parity checker and five test modules. Its
`deploy/shared-source.json` selects a full Infrastructure commit SHA. This is a
build-time dependency: the private release bundle contains the runtime script,
`app.json`, Compose and environment files needed for offline recovery.

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

Allowed route-network members and required members are separate configuration
fields. Gateway and current-app endpoints are required. Companion absence is
allowed during app recovery, while unexpected members, address/trust drift and
published-port drift fail. Both apps must pass gateway cutover acceptance.

The transaction stays in one file because its ordering and crash barriers form
one recovery state machine. Separating app policy and readiness predicates removes
unreachable code without scattering that state machine across artificial layers.

## 🔀 Intentional application differences

| Contract input | Notoli | MacroMapper |
| --- | --- | --- |
| App root | `/root/apps/notoli` | `/opt/apps/macromapper` |
| Services | `backend`, `frontend` | `macromapper-backend`, `macromapper-frontend` |
| Backend networks | private `/29` + separate egress | app ingress + app default/egress |
| Frontend networks | `notoli_default` | app ingress + app default |
| Trust/address | exact proxy `.2`, backend `.3`; Uvicorn peer handling preserved | canonical forwarded HTTPS behind restricted backend reachability |
| Published frontend port | existing IPv4/IPv6 3000 retained | none |
| Common readiness | direct API 401, public HTML 200 and JSON API 401 | same |
| Extra readiness | OAuth issuer/resource metadata and MCP challenge | none; functional AI/mail checks are separately authorized |
| Extra environment | MCP origin and trusted proxy | OpenAI key, model and timeout |
| Frontend build argument | `REACT_APP_API_BASE_URL=` | `VITE_API_BASE_URL=` |

## 🔒 Automated parity and updates

App CI's existing automation test gate runs `python3 deploy/check_parity.py`.
The checker fetches the manifest and workflow template at the pinned commit,
then compares common source/tests/checker hashes and the rendered workflow.
Unintended code, test or workflow changes fail CI. Windows CRLF is normalized;
other byte differences are rejected. Source retrieval failure also fails the gate.
All external production action references are pinned. The deployment build checks
parity again before accessing destination credentials or publishing images.

For a coordinated update:

1. Edit common source/tests/template here and run
   `python scripts/update_release_manifest.py`. Infrastructure CI verifies the
   manifest with `--check`.
2. Commit and review the shared changes. In both app PRs, set the same immutable
   commit in `deploy/shared-source.json`, then run
   `python deploy/check_parity.py --sync`. It copies the approved common files
   and renders the workflow using that app's configuration.
3. Run parity and the full deployment tests in each app. Review configuration or
   Compose differences explicitly; never edit only one vendored engine.

During local development, `--source-root <infrastructure-checkout>` performs the
same checks without network access. CI never uses this override. A version bump
is required for incompatible contract semantics; coordinate adoption in both app
PRs. Explicit pin changes are reviewable upgrades, not an automatic deployment.

## 🧪 Verification and operations

Both apps execute the same fault, SQLite/WAL, generation/checkpoint, timeout,
lock, readiness, missing-backend and retry tests. App-policy regressions retain
Notoli's exact trust/MCP behavior and MacroMapper's unpublished frontend/OpenAI
requirements. Real Docker recovery checks preserve companion container identity,
configuration, database bytes and a separate gateway fixture. The gateway's real
Nginx route/handoff/reversal tests remain in this repository.

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
`tests/fixtures/release-profiles` runs the same five release suites for Notoli,
MacroMapper, and the isolated template example in Linux/disposable-Docker CI.

The template profile is an onboarding example, not a third application approved
for the shared host. It does not add gateway routes, networks, certificates,
capacity, or deployment authorization. An operator must review the actual full
gateway topology, chosen subnet, bootstrap, locks, and capacity before activation.
All consumers must pin the same reviewed source commit when adopting this change.


## 🔌 Optional MCP applications

Follow the [optional MCP contract](optional-mcp.md) for app-owned ASGI/OAuth, shared ingress, readiness and rollback. Notoli remains enabled; MacroMapper is not advertised until its application registry is ready. Preserve independent releases and exact app proxy trust.
