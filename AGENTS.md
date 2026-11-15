# AGENTS.md

## 🧭 Ownership and shared rollout

FullStackTemplate owns reusable application engineering and the canonical MCP
Python framework. Infrastructure owns shared ingress, host operations and the
versioned application release engine. Each application owns its domain behavior,
credentials, OAuth issuer, consent, permissions and MCP tools; do not introduce a
shared authorization service, cross-application account mapping or YNAB dependency.

Follow the [shared rollout policy](https://github.com/VanillaIceCube/FullStackTemplate/blob/main/docs/SHARED-ROLLOUT-POLICY.md)
for reusable framework, automation, test or security changes. One canonical
FullStackTemplate parent must inventory all four repositories as required,
not applicable, already satisfied or explicitly deferred with reasons and evidence.
Infrastructure-owned deployment/host changes use an Infrastructure parent with
linked downstream work; do not relocate source ownership.
The parent is complete only after required downstream adoptions are merged and
verified, or explicitly deferred with an owner, tracking issue and acceptance.
Record final-head/main checks and exact PR/commit/evidence links; template-only
success is insufficient. Preserve active PRs, issue history, production controls
and non-triggering labels when consolidating work.

## 📚 Documentation ownership

The main README introduces the repository. Keep setup, commands, configuration,
and maintenance details in the owning folder README and its linked references.
Use consistent headings: 🧭 Structure, 💻 Local development, ⚙️ Configuration,
🧪 Checks, 🔌 MCP integration, and 📚 Reference where applicable.
See the [documentation index](docs/README.md) for scripts, validation, and other guides.
Keep this file current when its commands or constraints change, and update the
owning README/reference when setup, routing, environment, deployment or CI changes.
Record user-visible or operational changes in `CHANGELOG.md`.

GitHub setup belongs in [.github/README.md](.github/README.md), workflow behavior
in [.github/workflows/README.md](.github/workflows/README.md), and the shared
reviewer/action contract in [.github/actions/README.md](.github/actions/README.md).

## 📝 Changelog format

Keep the single `# Changelog` title and established introduction at the top;
never place entries above them. Use newest-first `## YYYY-MM-DD` sections,
reusing the existing date instead of creating a duplicate. Within each date,
use only nonempty `### Added`, `### Fixed`, `### Changed`, `### Removed` groups,
in that order, with no duplicate categories and entries filed under the correct
group. Use `- ` bullets and one blank line around headings. Preserve substantive
history and valid UTF-8 text when editing or merging entries.

## 💻 Local development

This repository owns shared ingress and release tooling rather than a Django/React
application. Use Python 3.12+, Node.js, Docker Engine/Compose and OpenSSL with a
disposable local/CI daemon; follow [.github/README.md](.github/README.md) and
[workflow checks](.github/workflows/README.md#-checks-and-diagnostics). Read the architecture and release standard
before changing topology or shared release behavior.

## ⚙️ Configuration

Use [nginx/README.md](nginx/README.md),
[app-release/README.md](app-release/README.md) and the
[operations guides](docs/README.md) for topology, release profiles and private
configuration. Preserve exact app proxy trust and independent app readiness;
application credentials remain in their owning app. Gateway deployment uses
repository Actions secrets/variables under the explicit authorization below.

## 🧪 Checks

Validate Compose configuration and the retained action-local regressions:

```sh
docker compose -f compose.yml config --quiet
python app-release/update_release_manifest.py --check
node --test .github/actions/*/*.test.js
```

For automation changes, run Actionlint and ShellCheck through
`.github/tools/lint_infrastructure.sh`. Shared behavior changes also require both
applications' deployment suites and pinned-source parity checks. Root ingress,
gateway, snapshot, release-profile and tooling suites have been retired; retained
checks do not establish runtime or recovery acceptance. Never execute the
production cutover procedure as a test.

## 🚀 Production

Ordinary changes merge through reviewed `main` before promoting an exact reviewed
source tree through the repository's existing `env-prod` process. Preserve all
required CI, reviews, owner authorization and recovery gates. Explicitly
owner-authorized deployment experiments must return promptly to `main` through
review before the next ordinary promotion. Preserve both histories and newer main
work; never reset or force-push to manufacture parity. Intentional release lag is
allowed while prerequisites or acceptance remain unfinished. History reconciliation
does not authorize deployment, and an absent production branch is not a reason
to create one. Follow the [main-first release policy](https://github.com/VanillaIceCube/FullStackTemplate/blob/main/docs/SHARED-ROLLOUT-POLICY.md#main-first-releases).

Common release code, tests, checker and workflow are owned by Infrastructure.
Change `app-release/v1` at the source, regenerate its manifest, then synchronize
all consumers to the same immutable source commit. Application repositories track
that source in `deploy/shared-source.json`; never edit only a vendored copy.
Preserve app-specific Compose, network/readiness policy, immutable image digests,
SQLite capture/recovery and explicit rollback. Keep shared ingress/certificates
and host operations within their separately authorized Infrastructure scope.

### Gateway promotion authorization

Infrastructure requires explicit owner approval for a merge to `main` and separate
authorization for `env-prod` promotion. The shared main-first rule above preserves
the owner-authorized experiment exception and both histories.

The owner's [October 19 decision](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4#issuecomment-6273538610)
authorizes automatic gateway deployment when the owner promotes reviewed main
source to `env-prod`. The owner-triggered promotion is production authorization;
no second reviewer or per-release approval variable is required. Manual retries
must also be owner-triggered. Initial host setup and explicit gateway recovery
retain their separately authorized operator scope. Application release rules
and the one-time cutover are unchanged.

The owner's [gateway settings decision in #41](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/41)
uses repository Actions secrets and variables only. No GitHub Environment or
Deployment API record is required. Preserve owner/branch/source/workflow checks,
credential-free authorization before key loading, restricted triggers, fingerprint
pinning, least privilege and host recovery evidence. Repository secrets have no
branch-scoped access boundary; arbitrary workflow writers remain privileged.
Document that exposure rather than claiming helper checks constrain other workflows.

## 🤖 GitHub automation

Preserve existing required checks, scanner/lint/test gates and reviewer budgets.
Eligible same-repository human and Dependabot PRs retain their reviewers; forks
remain excluded from secret-bearing reviews. Keep reviewer identities and
serialized writers separate, validated optional `AI_REVIEW_*` settings aligned,
and Dependabot lint auto-fixes disabled. External GitHub Actions use immutable
commit SHAs with version comments. Workflow updates do not authorize deployment.

The shared publisher fails after every `REQUEST_CHANGES`, including repeated or
unchanged verdicts; valid `APPROVE`/`COMMENT` pass and unavailable/invalid output
fails. Missing credentials, incomplete required major-upgrade briefs and oversized
diffs must fail visibly. The shared diff budget is 512 KiB. Obi-Wan's semver-major
Dependabot brief uses complete primary-source evidence; web search remains limited
to that review path. Run the repository's publisher regression tests and
Actionlint when changing this contract. Where used, the read-only `verify-gates.js` audit requires actual
successful reviewer results, including after cancelled or skipped runs.

Dependency review retains full JSON in the `dependency-review-evidence` artifact,
passes it through a file rather than environment variables, and limits RoboCop's
report to 16 KiB plus summary metadata. Disclose omitted entries; bounded reports
must not change the independent gate's non-success verdict. Missing evidence
fails. Preserve CodeQL scope outputs, full default-branch coverage and RoboCop
baseline evidence; concurrent security-alert closure requires verified final state.

Secret-dependent workflows fail visibly when credentials are unavailable.
RoboCop's short-lived App token reads alerts and authors issue mutations;
`SECURITY_ALERTS_TOKEN` is isolated to personal GitHub Project v2 synchronization.
Keep App IDs/private keys, least-privilege permissions, trigger policy and field
setup documented in `.github/README.md`. Security-alert variables resolve in the
three caller workflows, not local composite metadata; pass explicit model, effort
and token inputs. Run `.github/actions/custom-regressions/security-alert-contract.test.js`
after changes; actual loading acceptance requires fresh controlled dispatches on
corrected main. Preserve applicable bounded malware review and documented
coverage decisions. Maintain CI architecture diagrams and regenerate
`docs/CI-CD-SOURCE-INVENTORY.json` with `python .github/tools/ci_architecture.py` after
workflow edits. Promotion summaries are informational.

Require `Required CI`, preserve independent gates and applicable reviewer failures,
and keep manual owner merging. Trusted same-repository Dependabot PRs require the
same three reviewers as human PRs; production/Project-token secrets remain outside
Dependabot. Preserve non-mutating reviews. Dependabot security-update PRs do not
authorize merging, and a human PR smoke test does not prove Dependabot access.
Infrastructure has one publisher test file and no npm dependency graph; application
publisher/branch-gating tests and npm malware scanning are not automatic parity
requirements here. Keep the Infrastructure-specific Required CI and extra secrets
gate documented in the workflow guide.

## 🔑 OpenAI reviewer isolation

Use `OBI_WAN_OPENAI_API_KEY`, `LINT_EASTWOOD_OPENAI_API_KEY`, and
`ROBOCOP_OPENAI_API_KEY` for their respective reviewers; RoboCop also owns
all security-alert model calls. `OPENAI_REVIEWERS_PROJECT_ID` identifies this
repository's reviewer project. Keep credentials separate across repositories
and application environments, preserve visible missing-key failures, and follow
the credential ownership and cutover verification in `.github/README.md`.
Store the three reviewer OpenAI keys and three reviewer App private keys in both
Actions and Dependabot. Keep production, application, SSH and Project-token
secrets outside Dependabot. A human PR smoke test does not prove Dependabot access.

Use `gpt-6-luna` for OpenAI code, build and security reviewers and security-alert
grouping. Preserve each reviewer's key/project isolation, budgets and blocking
gates. Application AI model selection remains app-owned.

## 🔌 MCP integration

Shared MCP framework changes originate in FullStackTemplate's canonical Python
package; synchronize consumer hashes and pins. Derived applications own enablement,
registries, scopes and business tools. Infrastructure supplies ordinary gateway
routing and its optional MCP contract. Preserve existing Notoli credentials,
scopes, tool permissions, connection and exact proxy trust. The retired central
issuer is not a deployment prerequisite. Advertise an app service only after its
own registry, OAuth and readiness checks pass; framework adoption alone does not
authorize activation, client registration, owner consent or plugin installation.

Follow the [optional MCP contract](docs/optional-mcp.md) for app-owned ASGI/OAuth,
shared ingress, readiness and rollback. Notoli and MacroMapper route MCP/discovery
to their own backends. Preserve independent releases and each app's exact proxy
trust; do not apply app-specific scopes or credentials to Infrastructure.

## 🧩 Repository-specific contracts

Read the [architecture](docs/architecture-v2.md),
[release standard](docs/app-release-standard.md) and
[gateway guide](nginx/README.md) before related changes. Keep independent app
releases, existing network objects and Notoli's exact proxy trust intact. The
external YNAB integration and shared MCP issuer were retired by the owner on
October 30; follow the [retirement record](docs/mcp-retirement.md) and #96.

Owner decisions are recorded in
[issue #4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4).
Architecture/implementation approval does not authorize merging, release-branch
promotion or production operations. Use #4 for the designated operator and exact
production authorization. Repository automation in issues #5–#9 is owner-prioritized;
follow the workflow guide. Never run the production cutover guide as a test or
expose private recovery, environment or key data.
