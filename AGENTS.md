# AGENTS.md

## Human-First Engineering

This repository is intended to be understood, maintained, and owned by humans. AI-assisted development must not come at the expense of human comprehension.

### Simplicity and Readability

- Prefer simple, explicit, conventional implementations over clever or unnecessarily flexible solutions.
- Follow KISS, YAGNI, and separation of concerns without applying them dogmatically.
- Every abstraction, dependency, helper, and layer of indirection must justify its existence.
- Keep related functionality together. Minimize the number of files a developer must navigate to understand an operation.
- Prefer native framework and standard library functionality over custom implementations.
- Do not introduce abstractions for hypothetical future requirements.
- Prioritize readability over minimizing lines of code.
- Comments should explain why something exists, not restate what the code does.

### Deletion and Consolidation

- Prefer removing unnecessary complexity over introducing additional code to manage it.
- Remove unused imports, functions, files, dependencies, configuration, and obsolete implementation paths when verified safe.
- Maintain a single source of truth for business logic.
- Do not introduce parallel implementations, transitional wrappers, or compatibility layers without a demonstrated requirement.
- Leave modified code simpler or equally understandable whenever reasonably possible.

### Validation and Error Handling

- Address root causes rather than masking symptoms.
- Establish invariants and validate inputs at the appropriate upstream boundaries.
- Do not repeatedly validate conditions that are already guaranteed.
- Avoid speculative defensive checks, unnecessary fallbacks, broad exception handling, and silent failures.
- Unexpected internal failures should surface clearly.
- Preserve necessary security, authorization, data integrity, concurrency, external input validation, and legitimate recovery mechanisms.

### Testing

- Test meaningful, observable behavior rather than implementation details.
- Prefer straightforward tests with realistic inputs and minimal mocking.
- Do not create redundant tests solely to increase coverage.
- Do not weaken meaningful test coverage to make an implementation pass.
- Keep test infrastructure proportional to the complexity of the application.
- Follow established testing conventions.

### Architectural Consistency

- Understand existing conventions before introducing new patterns.
- Prefer extending an established, sound pattern over creating another.
- Maintain appropriate consistency across Notoli, MacroMapper, FullStackTemplate, and shared infrastructure.
- Where functionality is genuinely shared, maintain a canonical implementation through FullStackTemplate.
- Do not propagate unnecessary complexity in the name of parity.
- Respect legitimate product-specific requirements.

### Scope and Ownership

- Implement what was requested, not what might eventually be requested.
- Avoid unrelated refactoring and speculative improvements.
- Do not introduce new dependencies, architectural layers, or infrastructure without clear justification.
- Preserve existing behavior unless a behavioral change is explicitly intended.
- Flag consequential architectural decisions and uncertain deletions for human review.
- Verify changes using relevant tests, linting, type checks, and builds.

### Final Self-Review

Before completing any change, ask:

- Can this implementation be simpler?
- Is every new abstraction necessary?
- Can a human easily trace the execution flow?
- Am I solving a real problem or a hypothetical one?
- Am I addressing the root cause or masking it?
- Have I introduced unnecessary maintenance overhead?
- Would a human developer reasonably choose this implementation without AI assistance?

If a simpler, equally correct implementation exists, prefer it.



Complexity must be earned. Code is a liability as well as an asset. The objective is not to maximize output, but to deliver reliable functionality with the lowest reasonable maintenance burden.

## 🧭 Ownership and shared rollout

FullStackTemplate owns reusable application engineering and the canonical MCP
Python framework. Infrastructure owns shared ingress, host operations and the
versioned application release engine. Each application owns its domain behavior,
credentials, OAuth issuer, consent, permissions and MCP tools; do not introduce a
shared authorization service, cross-application account mapping or YNAB dependency.

Follow the [shared rollout policy](https://github.com/VanillaIceCube/FullStackTemplate/blob/main/.github/_README.md#-shared-engineering-ownership-and-rollout)
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
Use the owning folder READMEs linked below for setup and maintenance.
Keep this file current when its commands or constraints change, and update the
owning README/reference when setup, routing, environment, deployment or CI changes.
Record user-visible or operational changes in `CHANGELOG.md`.

GitHub setup belongs in [.github/_README.md](.github/_README.md), workflow behavior
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
application. Use the locked uv Python 3.12 tooling project, Node.js, Docker Engine/Compose and OpenSSL with a
disposable local/CI daemon; follow [.github/_README.md](.github/_README.md) and
[workflow checks](.github/workflows/README.md#-checks-and-diagnostics). Read the architecture and release standard
before changing topology or shared release behavior.

Install uv and run `uv sync --locked` from the repository root. The root
`pyproject.toml` and `uv.lock` own the pinned PyYAML tooling environment. The project
`requires-python` constraint selects Python 3.12. Run Python checks through `uv run --locked`. Install the Node automation parsers from `.github/package-lock.json` before running JavaScript checks. Runtime gateway/release scripts do
not require uv on production hosts. See the GitHub workflow guide for coverage.

## ⚙️ Configuration

Use [gateway/README.md](gateway/README.md),
[deploy/README.md](deploy/README.md) and the
[gateway operations](gateway/README.md#-operations) for topology, release profiles and private
configuration. Preserve exact app proxy trust and independent app readiness;
application credentials remain in their owning app. Gateway deployment uses
repository Actions secrets/variables under the explicit authorization below.

## 🧪 Checks

Validate Compose and run the automation tests locally.

```sh
docker compose -f compose.yml config --quiet
npm ci --prefix .github --ignore-scripts --no-audit --no-fund
node .github/scripts/run-automation-tests.js
```

For automation changes, run the checks in
[the Infrastructure lint workflow](.github/workflows/gate-lint.yml). Shared
behavior changes also require both applications' deployment suites and
pinned-source parity checks. The [gateway integration test](.github/tests/integration/gateway.test.js)
exercises routing, exact proxy trust and gateway configuration on disposable networks.
Use the operator guide for live launch acceptance. Never execute the
production cutover procedure as a test.

## 🚀 Production

Ordinary changes merge through reviewed `main` before promoting an exact reviewed
source tree through the repository's existing `env-prod` process. Preserve all
required CI, reviews, owner authorization and readiness checks. Explicitly
owner-authorized deployment experiments must return promptly to `main` through
review before the next ordinary promotion. Preserve both histories and newer main
work; never reset or force-push to manufacture parity. Intentional release lag is
allowed while prerequisites or acceptance remain unfinished. History reconciliation
does not authorize deployment, and an absent production branch is not a reason
to create one. Follow the [main-first release policy](https://github.com/VanillaIceCube/FullStackTemplate/blob/main/.github/_README.md#main-first-releases).

Common release code, verification, tests and workflow are owned by Infrastructure.
Change `deploy/` in Infrastructure, then synchronize all consumers to that exact Git commit. Application repositories track
that source in `shared_source` in `deploy/production/app.json`; never edit only a vendored copy.
Preserve app-specific Compose, network/readiness policy, immutable image digests,
SQLite writer integrity and private pre-migration copies of the database and app
containers. A failed deployment health check takes both app services offline. Keep shared ingress/certificates
and host operations within their separately authorized Infrastructure scope.

### Gateway promotion authorization

Only verified eligible Dependabot updates may request protected auto-merge to `main`.
Every other merge requires the owner’s decision. Production always requires separate owner authorization for `env-prod` promotion. The shared main-first rule above preserves
the owner-authorized experiment exception and both histories.

The owner's [October 19 decision](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4#issuecomment-6273538610)
authorizes automatic gateway deployment when the owner promotes reviewed main
source to `env-prod`. The owner-triggered promotion is production authorization;
no second reviewer or per-release approval variable is required. Manual retries
must also be owner-triggered. Initial host setup requires separate operator authorization. Application release rules
and the one-time cutover are unchanged.

The owner's [gateway settings decision in #41](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/41)
uses repository Actions secrets and variables only. No GitHub Environment or
Deployment API record is required. Preserve owner/branch/source/workflow checks,
credential-free authorization before key loading, restricted triggers, fingerprint
pinning, least privilege and observed host readiness. Repository secrets have no
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
diffs must fail visibly. The shared diff budget is 2 MB (2,000,000 bytes). Obi-Wan's semver-major
Dependabot brief uses complete primary-source evidence; web search remains limited
to that review path. Run the repository's publisher regression tests and
Actionlint when changing this contract. Where used, the read-only `validate-reviewer-gates.js` audit requires actual
successful reviewer results, including after cancelled or skipped runs.

Dependency Review uses standard input for scanner outputs and limits RoboCop's
report to 16 KiB, including summary metadata. GitHub's native review summary and
workflow logs provide diagnostics. Disclose omitted entries; bounded reports
must not change the independent gate's non-success verdict. Missing evidence
fails. Preserve CodeQL scope outputs, full default-branch coverage and RoboCop
baseline evidence; concurrent security-alert closure requires verified final state.

Secret-dependent workflows fail visibly when credentials are unavailable.
RoboCop's short-lived App token reads alerts and authors issue mutations;
`SECURITY_ALERTS_TOKEN` is isolated to personal GitHub Project v2 synchronization.
Keep App IDs/private keys, least-privilege permissions, trigger policy and field
setup documented in `.github/_README.md`. Security-alert variables resolve in the
three caller workflows, not local composite metadata; pass explicit model, effort
and token inputs. Run `.github/tests/track-security-alerts.test.js`
after changes; actual loading acceptance requires fresh controlled dispatches on
corrected main. Keep advisory-based malware alert tracking and document PR scanner coverage. Keep the CI architecture diagrams aligned with workflow edits.

Require `Required CI`, preserve independent gates and applicable reviewer failures,
and use the protected Dependabot Policy follow-up for eligible patch/minor updates.
Other merges remain manual. Trusted same-repository Dependabot PRs require the
same three reviewers as human PRs; production/Project-token secrets remain outside
Dependabot. Preserve non-mutating reviews. Dependabot security-update PRs do not
authorize merging, and a human PR smoke test does not prove Dependabot access.
Infrastructure has one publisher test file and an npm lockfile for its GitHub automation. Its PR dependency gate reviews dependency changes; the application-specific malware gate also scans frontend and backend lockfiles. Keep Infrastructure's Required CI aggregation documented in
the workflow guide. It includes the shared secret scan.

## 🔑 OpenAI reviewer isolation

Use `OBI_WAN_OPENAI_API_KEY`, `LINT_EASTWOOD_OPENAI_API_KEY`, and
`ROBOCOP_OPENAI_API_KEY` for their respective reviewers; RoboCop also owns
all security-alert model calls. `OPENAI_REVIEWERS_PROJECT_ID` identifies this
repository's reviewer project. Keep credentials separate across repositories
and application environments, preserve visible missing-key failures, and follow
the credential ownership and cutover verification in `.github/_README.md`.
Store the three reviewer OpenAI keys and three reviewer App private keys in both
Actions and Dependabot. Keep production, application, SSH and Project-token
secrets outside Dependabot. A human PR smoke test does not prove Dependabot access.

Use `gpt-6-luna` for OpenAI code, build and security reviewers and security-alert
grouping. Preserve each reviewer's key/project isolation, budgets and blocking
gates. Application AI model selection remains app-owned.

## 🔌 MCP integration

Shared MCP framework changes originate in FullStackTemplate's canonical Python
package; synchronize reviewed runtime changes across consumers and record source
commits in the coordinated tracking issue. Derived applications own enablement,
registries, scopes and business tools. Infrastructure supplies ordinary gateway
routing and its optional MCP contract. Preserve existing Notoli credentials,
scopes, tool permissions, connection and exact proxy trust. The retired central
issuer is not a deployment prerequisite. Advertise an app service only after its
own registry, OAuth and readiness checks pass; framework adoption alone does not
authorize activation, client registration, owner consent or plugin installation.

Follow the [optional MCP contract](gateway/README.md#-optional-mcp-contract) for app-owned ASGI/OAuth,
shared ingress and launch readiness. Notoli and MacroMapper route MCP/discovery
to their own backends. Preserve independent releases and each app's exact proxy
trust; do not apply app-specific scopes or credentials to Infrastructure.

## 🧩 Repository-specific contracts

Read the [architecture](gateway/README.md#-structure-and-ownership),
[release standard](deploy/README.md) and
[gateway guide](gateway/README.md) before related changes. Keep independent app
releases, existing network objects and Notoli's exact proxy trust intact. The
external YNAB integration and shared MCP issuer were retired by the owner on
October 30; follow the [owner decision in #96](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/96).

Owner decisions are recorded in
[issue #4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4).
Architecture/implementation approval does not authorize merging, release-branch
promotion or production operations. Use #4 for the designated operator and exact
production authorization. Repository automation in issues #5–#9 is owner-prioritized;
follow the workflow guide. Never run a production cutover as a test or
expose private environment, database or key data.
