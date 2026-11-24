# 🔄 GitHub workflows

CI, reviews, dependency/security checks, and release behavior for JudeAndrewAlabaInfrastructure.

## 🧭 Workflow map

| Area | Entry points |
| --- | --- |
| Pull requests | [CI orchestrator](ci-orchestrator.yml), independent gates, and the three reviewer workflows. |
| Dependabot | [Protected auto-merge follow-up](ci-auto-merge.yml) after successful PR CI. |
| Security alerts | [CodeQL](alert-codeql.yml), [vulnerability](alert-vulnerability.yml), and [malware](alert-malware.yml) aggregation after the nightly scan or on a daily schedule, with manual dispatch for every feed. |
| Releases | [Release workflow](deploy-gateway.yml). |

Workflow YAML is authoritative for triggers, permissions and job dependencies.
Read [repository setup](../README.md) before expecting secret-dependent workflows
to succeed. Commands in this guide run from the repository root.

## 🔄 Pull requests and reviews

CI runs on pull requests targeting any branch except `env-prod`. A new run
cancels the older run for the same pull request.

### Major-upgrade review evidence

Obi-Wan uses Dependabot's per-dependency metadata for grouped upgrades.
Release lookups use each major update's own ecosystem and target version.
Repository usage searches cover every listed dependency and retain the
tracked-file exclusions and 30,000-byte limit. Numeric Actions references
such as 7 and v7 can match a full release tag such as v7.0.0. Opaque refs
leave a visible evidence gap. Required briefs need at least one valid HTTP(S)
source URL. The publisher keeps independent body findings when it suppresses
duplicate inline comments or sees an unchanged verdict.

<a id="-ai-reviewer-parity-across-repositories"></a>

### AI reviewer parity across repositories

The common contract is all three reviewers on trusted same-repository human
and Dependabot PRs, no secret-dependent reviews on forks, separate per-persona
OpenAI keys within each repository, six reviewer secrets in each secret store,
and visible failure for unavailable reviews. Infrastructure's implementation
now adopts this eligibility contract; live acceptance still requires real
Dependabot credentials and a Dependabot-triggered run after owner merge.

| Repository | Human / Dependabot AI reviews | Reviewer secret stores | Intentional merge-policy difference |
| --- | --- | --- | --- |
| MacroMapper | All three / all three | Actions + Dependabot | Existing eligible dependency auto-merge and app-specific required checks |
| Notoli | All three / all three | Actions + Dependabot | Existing eligible dependency auto-merge; reviewer branch-policy work is separate |
| FullStackTemplate | All three / all three | Actions + Dependabot | Existing eligible dependency auto-merge and required reviewer child checks |
| Infrastructure | All three / all three | Actions + Dependabot | Eligible Dependabot auto-merge plus Required CI. Other merges use the owner process. |

Independent checks, evidence limits and major-upgrade gaps remain specific to
each repository's actual scanners and dependency ecosystems. Infrastructure
retains its non-mutating lint reviewer, immutable actions,
repository-scoped App tokens and production credential boundary. Parity of
review eligibility does not copy application deployment or auto-fix behavior.

After owner-approved merge, update or rerun a real same-repository Dependabot PR
using the new default-branch policy; an old run retains its original workflow
revision. Verify the run actually uses the new policy, all three App identities,
required review outcomes, and supported major-upgrade evidence or documented
gaps. A human PR run does not prove access to the Dependabot secret store.

<a id="-workflow-supply-chain-controls"></a>

### Workflow supply-chain controls

The workflow security checker and mocked regressions reject mutable external
Action references, missing version comments, broad permission grants and privileged
PR-target triggers. Run `node .github/actions/check-workflow-security/check-workflow-security.js`
and its `*.test.js` suite locally. Repository defaults were independently audited
as read-only with workflow-token PR approvals disabled. GitHub App reviewers keep
their separate credentials and explicit grants. SHA enforcement is enabled only
after source compliance and required final-head validation.

Repository Actions secrets are not branch-scoped: writers able to install arbitrary
workflows remain privileged. This helper validates checked-in policy but cannot
constrain a workflow that bypasses it. GitHub rulesets and independent review
remain necessary. The checker parses YAML nodes, including quoted/flow/sequence
forms, rejects aliases, duplicate and merge keys, and requires pinned PyYAML 6.0.3.

Declare permissions explicitly in the workflow or job. The checker rejects broad
grants such as `write-all` and unknown permission scopes or levels. PR CI compares
each workflow and job's effective write scopes to the same path and job on its
exact base commit. New workflows and jobs start with no approved write scopes.
The required default-branch policy repeats this comparison for main PRs using
reviewed code and Git blobs. It never executes proposed workflows. A deliberate
increase requires an independently reviewed change to the trusted policy.

## 🔒 Merge and dependency controls

<a id="-required-checks-and-permissions"></a>

### Required checks and permissions

`Required CI` in the CI workflow requires independent gates and all applicable reviews.
Failed/cancelled/unexpectedly skipped checks block it. REQUEST_CHANGES,
unavailable AI output and diff overflow fail reviewer checks. Inline placement,
prior-history and duplicate suppression are tested. Bot approval never
authorizes merging or deployment.

Same-repository human and Dependabot PRs require all three AI reviewers as
well as every independent gate. Fork PRs run the independent read-only gates
without receiving reviewer secrets. There is no `pull_request_target` workflow.
Dependabot uses its separate secret store for all six reviewer credentials;
missing credentials or skipped applicable reviews fail Required CI. Obi-Wan's
existing metadata/major-upgrade evidence path applies to Dependabot updates,
with web search enabled only for major upgrades and explicit gaps for unsupported
evidence. Only the protected Dependabot policy can automatically request a main merge.
Owner approval governs other merges and production promotion.

GITHUB_TOKEN begins with contents read. Only CodeQL upload/review jobs request
additional permissions. App tokens name this repository and explicit permissions;
Lint Eastwood receives contents read despite its existing broader account
installation. Checkout does not persist credentials. Review/scanner workflows
never request contents write, commit fixes, merge or deploy. The separately
approved gateway workflow below uses isolated production credentials.

Alerts serialize each feed, validate every source ref exactly once, and manage
only `infrastructure-security-alert` issues. Missing credentials, unavailable
feeds, malformed AI JSON or absent Project metadata fail visibly. Source links
remain; secret and private host/recovery contents are excluded.

## 🛡️ Security and alerts

### Protected Dependabot auto-merge

After a successful PR CI run, the follow-up checks out reviewed `main` and resolves
the run to the exact open PR head. It publishes a fresh `Dependabot Policy` check.
Human and fork PRs follow the manual merge process after the trusted workflow
write-grant comparison succeeds. Eligibility is limited to same-repository Dependabot PRs targeting
`main` with exactly one verified Dependabot-authored commit. Every dependency in
the signed metadata must be a patch or minor update. Any matching open alert
needs a known CVSS score at most 6.9. Version and security updates share this policy.
Major and SHA-only Actions updates require a manual decision. Unverified metadata,
missing approvals, unavailable checks and unsafe alert scores fail the policy.

Before enabling native auto-merge, the follow-up checks all active branch
requirements, the Infrastructure lint and validation jobs, Dependency Review,
Gitleaks, CodeQL scope and analyzers, and each
reviewer job. CodeQL skips require matching changed paths, including paths
before renames. All three reviewer bots must approve the current head. The
policy waits for its own check to be visible and in progress. A previous run's
successful check cannot satisfy that check. GitHub receives the expected head
SHA and enforces branch protection. No workflow requests a production promotion.
The shared policy accepts check runs produced by GitHub Actions. Adding a
required check from another provider pauses automatic merging for owner review,
even if that provider reports success. The native rules still govern manual merges.
See [repository setup](../README.md#-branch-protection) for activation.

### Infrastructure checks

PR CI calls the [lint gate](gate-lint.yml) and [test gate](gate-test.yml) once. The test check keeps its existing name, `Tests / validate`. Required CI requires both results. For same-repository PRs, Required CI also checks that its read-only token can read main’s status rules and that GitHub supports the expected-head guard for native auto-merge.

| Capability | Behavior |
| --- | --- |
| Obi-Wan Code-nobi | Infrastructure correctness, maintainability, valid inline comments and prior-review history |
| Lint Eastwood | Interprets actionlint/ShellCheck, Compose, ingress/reversal, SQLite recovery and automation diagnostics; never edits source |
| RoboCop | Interprets authoritative scanner evidence and infrastructure security risks |
| CodeQL | Changed paths select PR languages. Daily runs at midnight Pacific (America/Los_Angeles) and manual runs scan all three languages. |
| Dependency Review | New high/critical vulnerable dependencies block PRs; Actions use GitHub's dependency graph |
| Package malware | No PR package-malware scanner is configured. The separate alert feed tracks existing malware advisories. |
| Secrets | Gitleaks on PRs plus repository secret scanning and push protection |
| Dependabot | Weekly grouped Actions and separate Compose updates, limits, owner assignment and existing labels |
| Security alerts | Daily/manual CodeQL, all-severity vulnerabilities and advisory-classified malware, RoboCop issues and Project #13 metadata |

Daily CodeQL scans refresh the default-branch baseline. Required PR
checks continue to scan changed languages before merge. Security-tab findings
for newly merged code can lag until the next full scan completes. Daily alert
tracking runs after the scheduled scan succeeds. To refresh all three languages
sooner, select **Actions → CodeQL Gate → Run workflow → main**, or run
`gh workflow run gate-codeql.yml --ref main`. Check the run and its analyzed
commit before relying on the updated default-branch baseline.

CodeQL/Dependency Review do not scan Nginx configuration or image contents for
malware/CVEs. Disposable Nginx tests cover actual routing, DNS, forwarding/trust,
logging and reversal. Before production promotion, an operator reviews the image and advisory evidence
and separately authorizes deployment.

<a id="-dependency-evidence-and-alert-lifecycle-parity"></a>

### Dependency evidence and alert lifecycle parity

The reusable baseline is FullStackTemplate's `.github/actions/prepare-vulnerability-report`.
MacroMapper, Notoli and Infrastructure carry the same report implementation and
regression contract. Dependency Review still blocks high/critical additions;
every non-success scanner outcome, missing/malformed output or failed evidence
preparation fails the independent Vulnerability check. No empty-array fallback
may turn unavailable evidence into a clean scan. RoboCop receives at most 16 KiB
of package/severity/manifest context, with omitted-entry counts. The
`dependency-review-evidence` artifact retains every structured entry for seven
days, excluding untrusted free text and arbitrary URLs; unavailable evidence is
retained as structured diagnostics. Artifacts have the repository's Actions
access controls, not an additional private storage boundary.

Alert synchronization saves source history/replacement links first, ensures
Project membership, then writes End date before Status Done. Done can trigger
Project auto-close. The issue client re-reads state before a separate state-only
close. Only GitHub's observed HTTP 422 `Validation Failed` with an empty errors
array is eligible for recovery, and only if another read proves closed/completed
with the exact saved lifecycle body. Other failures propagate. Partial Project
failures leave the issue open for rerun; issue mutations remain attributed to
RoboCop and Project writes use the separate Project credential. New items use
the live `Work type` field. No credentials, branch protections or deployments
change.

Historical evidence: FullStackTemplate #192 closed at 2026-10-11 16:40:51 UTC,
before run 38156425534's state-close PATCH returned 422 at 16:40:52 UTC with
`errors: []`. Notoli #825 has the same earlier pattern. All four Projects have
Auto-close issue enabled (read-only verification 2026-10-20). This establishes
the competing-close ordering; GitHub's internal validation cause is not exposed.
Mocks reproduce that interleaving and reject unrelated errors. Empty scheduled
feeds do not establish that a live close race occurred.

Infrastructure deliberately retains weekly grouped Actions and separate Compose
Dependabot updates, all-language CodeQL on scheduled and manual runs, `pull-requests: read` for
Dependency Review, immutable actions and the separate secret-scanning gate.
Dependency graph evidence covers supported Actions/Compose dependencies; it is
not an image-content scanner and does not assume backend/frontend directories.

<a id="-compatible-codeql-updates"></a>

### Compatible CodeQL updates

The current CodeQL entry points use the same immutable v4.39.3 revision.

Dependabot groups all `github/codeql-action` entry points (including `init`,
`analyze`, `autobuild` and `upload-sarif`) in `codeql` version-update PRs.
A separate `codeql-security` group applies the same matching to security updates;
GitHub does not combine version and security updates in one group. Keep both
patterns (`github/codeql-action` and `github/codeql-action/*`) so repository and
entry-point dependency names match. Review every CodeQL entry point together,
keep their immutable revisions aligned, and preserve normal CI/reviewer gates.

The applications retain daily updates. Infrastructure retains weekly updates,
its owner/labels/PR limits, general Actions group for non-CodeQL updates, and
separate Compose updates. The template aligns its mutable CodeQL tag with the other repositories'
immutable v4.39.1 revision. Scanner scope, permissions and merge/deployment
gates remain unchanged. Canonical rollout:
[FullStackTemplate #271](https://github.com/VanillaIceCube/FullStackTemplate/issues/271).

<a id="-atomic-codeql-regression-guard"></a>

### Atomic CodeQL regression guard

FullStackTemplate is the canonical application Dependabot policy (#240).
Infrastructure adopts the common CodeQL revision guard and negative tests before
its required scope detection: every CodeQL entry point in `.github` must use
the same full immutable SHA. Split init/analyze, cross-workflow drift, mutable
tags and missing analysis fail visibly. The version/security update groups
merged in #106 remain unchanged, including weekly cadence and separate Compose
updates. Run `node --test .github/actions/check-codeql-pins/*.test.js` locally.

The protected Dependabot follow-up checks Required CI and all three current-head
reviewer approvals. Fork credentials and production/recovery authorization remain separate. Successful Dependabot
review evidence already exists on #53 and #33; human implementation PRs alone
do not prove Dependabot secret access. No shared app-release behavior changes.

The CodeQL guard parses YAML structurally with `PyYAML==6.0.3` (safe loading),
including flow mappings, quoted/escaped keys, folded values and aliases. Install
the locked parser for local Node regressions: `uv sync --locked`, followed by
`uv run --locked node --test <test files>`.

### Security-alert recovery

Each feed serializes scheduled and manual reconciliation. Before issue writes,
source coverage must be complete and unique. A valid model draft that omits refs
gets deterministic source-linked work items and an explicit warning; malformed
JSON, invalid schemas, unknown refs and duplicate memberships fail before writes.
Existing managed source refs select the canonical issue even when wording changes.

Project attachment retries transient failures at most three times, reading back
possibly committed writes before retrying. Unresolved attachments identify the
saved issue; rerun the same feed to reuse it. Reconciliation fills missing fields.
A group containing a critical alert receives P0. High or unknown severity raises
an existing P2/P3 group to P1. Other vulnerability groups default to P2. CodeQL and
malware groups default to P1. An urgent alert can raise an existing group's priority.
Higher priorities and other populated planning fields are preserved. All active groups synchronize before
superseded issues can close. Closure saves source history and End date before Done.
Only the observed empty-error or exact Issue/custom concurrent-close HTTP 422 may
recover, and only after readback proves closed/completed with the exact saved body.
All other errors remain failures. A successful empty feed does not exercise the race.

Infrastructure uses weekly Dependabot updates and requires its own CI aggregate and scanner contexts for protected auto-merge.

Malware lookup retains per-source-GHSA requests and rejects mismatched or unknown advisory classifications before writing the source checkpoint or changing issues. Empty feeds make no advisory requests.

### Security-alert configuration contract

The three `alert-codeql.yml`, `alert-vulnerability.yml`, and `alert-malware.yml`
workflows resolve `AI_REVIEW_MODEL`, `AI_REVIEW_REASONING_EFFORT`, and
`AI_REVIEW_MAX_OUTPUT_TOKENS` in their supported workflow `vars` context. They
pass explicit `model`, `reasoning-effort`, and `max-output-tokens` inputs to the
security-alert composite. Do not reference repository `vars` inside composite
manifests: GitHub rejects that metadata before alert fetching starts (#300).

Absent or empty values deliberately preserve `gpt-6-luna`, `medium`, and `16000`.
Nonempty overrides pass through the existing Responses policy. Configuration is
validated before source reads or issue/Project writes, including empty feeds;
invalid models, efforts or token limits fail visibly without a provider call.
All three feeds check the Project token and field schema before reading alerts.
RoboCop receives issue write access and read access to the selected feed.
Only the Project client receives the personal Project token.

`node --test .github/actions/custom-regressions/security-alert-contract.test.js`
checks actual YAML inputs/callers, audits local composites for unsupported `vars`,
and executes manifest-derived configuration, fetching, nested Responses shell,
validation and reconciliation code using synthetic feeds and mocked provider/API
writes. Existing lifecycle tests still cover complete accounting, partial-progress
recovery and the exact concurrent-close HTTP 422 case. These fixtures are not a
GitHub runner. After a reviewed repair, run one fresh controlled dispatch of each
alert workflow from corrected `main`, after checking managed labels/Project side
effects. Record runner loading/empty-feed evidence separately from nonempty mock
coverage; never rerun an old failed revision as proof of the new source.

## 🚀 Releases and promotion

Infrastructure owns the independent shared gateway and release-engine source.
Use [gateway releases and recovery](../../nginx/README.md#-operations) and the
[application release standard](../../app-release/README.md) for current
owner/source/branch controls. Application source or CI approval does not authorize
host operations. Preserve immutable accepted state, locks and explicit recovery.

<a id="-gateway-release-workflow"></a>

### Gateway release workflow

`deploy-gateway.yml` handles only separately authorized `env-prod` promotions
and explicit manual retries/rollback on that branch. It is disabled until the
repository enable variable, reviewed source/workflow and owner/branch validation
and private host adoption prerequisites are established. It uses separate
production credentials, persistent host transactions, exclusive maintenance
locking and gateway-only recovery. Review/scanner workflows cannot deploy.
Like the Notoli and MacroMapper deployment workflows, an authorized promotion
to `env-prod` starts deployment without a second reviewer or per-release
approval variable. Source PRs still require the normal main-branch checks.
See [gateway releases](../../nginx/README.md#-operations) for setup, bounded probes,
relevant-change policy, Actions evidence, interruptions and retention. Gateway SSH
configuration lives only in repository Actions settings; no GitHub Environment
or Deployment API record is required. Repository-wide key exposure and the
reviewed-workflow/write-access boundary are documented in that guide.

### Architecture and production summaries

The [canonical architecture reference](README.md#-architecture-and-trust-boundaries) maps PR/fork/
Dependabot paths, required checks, reviewer interactions, scheduled alerts,
main-to-env-prod/manual release paths and credential trust boundaries to source.

## 🧪 Checks and diagnostics

<a id="-validation-and-activation"></a>

### Validation and activation

The [lint gate](gate-lint.yml) runs only through pull-request CI.
The [test gate](gate-test.yml) runs through the CI orchestrator and selects checks
from the pull request's changed files. It runs applicable checks in this order.

| Check | Changes that trigger it |
| --- | --- |
| Compose configuration | Root Compose, Nginx, gateway deployment workflow, test gate, CI orchestrator, or Git attributes. |
| Shared release manifest and consumer release/recovery tests | Release source, Python tooling, test gate, CI orchestrator, or Git attributes. |
| JavaScript action regressions | GitHub configuration and automation, Python project or lockfile, or Git attributes. |

A failed prerequisite stops later checks. If path detection fails, the test gate fails.
The gate succeeds when no checks apply and reports automation as not applicable.

Use Node 24, uv with the locked Python 3.12 project, Docker, OpenSSL, ShellCheck,
and [Actionlint 1.7.12](https://github.com/rhysd/actionlint/releases/tag/v1.7.12)
on your PATH.

```sh
docker compose -f compose.yml config --quiet
uv run --locked python app-release/update_release_manifest.py --check
uv run --locked node --test .github/actions/*/*.test.js
actionlint -ignore 'unknown permission scope "vulnerability-alerts"'
uv run --locked node .github/actions/check-workflow-security/check-workflow-security.js
git ls-files -z --cached --others --exclude-standard -- '*.sh' | xargs -0 -r shellcheck
git ls-files -z --cached --others --exclude-standard -- '*.js' | xargs -0 -r -n 1 node --check
uv run --locked python -m compileall -q nginx app-release
```

The [lint workflow](gate-lint.yml) verifies the checksum of its pinned Linux amd64
Actionlint release. CI captures bounded diagnostics while enforcing the original
exit status. Shared release changes require a regenerated manifest and matched
consumer pins.

CI report files are decoded as UTF-8 with replacement for malformed bytes. Gateway
evidence always goes to stdout; it also appends UTF-8 text when a nonempty
`GITHUB_STEP_SUMMARY` path is configured. Only validated identities and fixed prose
belong in this evidence; never include credentials or private recovery output.

See [setup](../README.md#-before-your-first-pull-request). Default-branch Dependabot/schedules activate after
owner merge. The unmerged feature PR proves checks and identities, not scheduled
activation. No merge, promotion or production operation is implied.

Infrastructure validation checks Compose configuration, the canonical shared
release manifest, release/recovery tests, and action-local Node regressions. Compose and action-test failures still fail the
validation job. The root ingress, gateway transaction/retirement, snapshot,
release-profile matrix, automation-policy and bounded-log suites were retired.
When the release scope applies, CI syncs the proposed canonical source and all
five test modules into a disposable, commit-pinned FullStackTemplate checkout.
The tests use its application policy and the hosted runner’s Docker engine.
The recovery output passes their status and bounded diagnostics to the build reviewer.
The retired ingress suite reports `not-applicable`.

<a id="-automation-regressions-and-bounded-diagnostics"></a>

### Automation regressions and bounded diagnostics

See [the shared inventory](README.md#-coverage-boundaries). Actual composite
request construction and prior-review collection run with mocked curl/GitHub reads,
not live paid API calls. Diagnostic preprocessing remains active, bounding context
to 16,000 characters and artifacts to about 1 MiB per log for seven days; its root
regression test has been retired. Complete output remains in the job log.
The lint and validation workflows pass those excerpts to the build reviewer.

The shared YAML regression suite checks aliases, flow syntax, and explicit
permission mappings.
Repository writers remain privileged; this linter is not a security sandbox.
Infrastructure retains its existing shellcheck, Compose, secret scan, manifest,
RequiredCI and independent gateway controls. Application browser tests and npm
malware gates are not applicable here.

<a id="-locally-runnable-reporting-helpers"></a>

### Locally runnable reporting helpers

Guard runner-only output/summary variables. CI reports must preserve identical
framing and bounded evidence through output-file and unset-variable stdout
modes, using unpredictable delimiters. Test missing logs, malformed UTF-8 and
absent/empty/configured summary paths with disposable fixtures; preserve the
snapshot cleanup and primary-error behavior covered by the existing tests.

Validate syntax and relevant behavioral tests after automation changes. Preserve
original check failures and bounded/redacted diagnostics. Use disposable fixtures
for validation.

<a id="-related-guides"></a>

## 📚 Reference

- [Repository setup and credentials](../README.md).
- [Local actions and reviewer contract](../actions/README.md).
- [CI/CD architecture and trust boundaries](README.md#-architecture-and-trust-boundaries).

## 🗺️ Architecture and trust boundaries

Workflow YAML and protected-branch rules remain authoritative. FullStackTemplate
owns reusable application/reviewer patterns; Infrastructure owns the gateway and
versioned application release engine. Intentional app and Infrastructure policies
remain distinct.

### PR paths and required evidence

```mermaid
flowchart TD
    PR["PR opened, updated, reopened, or marked ready<br/>Target branch: any except env-prod"]
    CI["ci-orchestrator.yml"]
    L["gate-lint.yml<br/>Lint and formatting"]
    T["gate-test.yml<br/>Changed files select tests"]
    Q["gate-codeql.yml<br/>Changed files select analyzers"]
    V["gate-vulnerability.yml<br/>Dependency vulnerability review"]
    M["gate-malware.yml<br/>npm malware · app repos only"]
    S["gate-secrets.yml<br/>Gitleaks scan"]
    RC["review-code.yml · Obi-Wan"]
    RB["review-build.yml · Lint Eastwood"]
    RS["review-security.yml · RoboCop"]
    DONE["CI finishes<br/>All gates and applicable reviews report results"]
    AUTO["ci-auto-merge.yml<br/>Successful PR CI proceeds to Dependabot policy evaluation"]
    PR --> CI
    CI --> L & T & Q & V & S
    CI -->|"App repos only"| M
    CI --> RC
    L & T --> RB
    Q & V & S --> RS
    M --> RS
    L & T & Q & V & M & S --> DONE
    RC & RB & RS --> DONE
    DONE --> AUTO
```

[The orchestrator](ci-orchestrator.yml) runs on pull requests targeting any branch except `env-prod`. Same-repository human and Dependabot PRs
receive the configured reviewers. Forks receive no reviewer credentials: never
execute fork code with privileged credentials or add `pull_request_target` here.
Obi-Wan starts independently; Lint Eastwood consumes lint/test outcomes; RoboCop
consumes scanner evidence, including the secret scan. Missing evidence,
credentials, invalid output and `REQUEST_CHANGES` fail. Skipped or old-head reviews
are not current-head acceptance. The Dependabot follow-up verifies the exact head using reviewed main code.
Infrastructure also requires its Required CI aggregate. Production promotion is a separate owner action.

### CodeQL scans

```mermaid
flowchart LR
    PR["PR CI"] -->|"Select analyzers by changed files"| Q["gate-codeql.yml"]
    WEEK["Daily · midnight Pacific"] -->|"Full scan"| Q
    MANUAL["Manual · Run workflow"] -->|"Full scan"| Q
    Q --> F["Publish CodeQL findings to GitHub"]
```

### Reviewer data and write boundary

The [action contract](../actions/README.md) owns byte/page/count limits, identity,
serialized writers and reconciliation proof. Discussion and tool output are
untrusted data: they cannot authorize commands, secret disclosure, merges or
suppressed findings. Unavailable/truncated context is disclosed. Only provably
replaced, own-App feedback may be reconciled; human/other-bot threads remain open.
Reconciliation never dismisses a blocking verdict or changes required checks.
Each repository/persona retains separate credentials and the accepted Luna model.
Usage/cost estimates are partial and dated; unknown charges remain unknown.
Web search stays limited to Dependabot major-upgrade code reviews.

[Repository setup](../README.md) owns exact secret/variable names and installation
permissions. Dependabot receives required reviewer OpenAI keys/App private keys,
never production/Project credentials. RoboCop owns security-alert issue writes;
the separate Project token only synchronizes Project fields. Repository Actions
secrets are not branch-scoped: arbitrary workflow writers remain privileged.
External Actions use immutable pins. Workflow reviews cover changes to write
permissions in the workflow or job that requests them.

### Scheduled source-alert maintenance

```mermaid
flowchart TD
    MIDNIGHT["Every day · midnight Pacific"]
    SCAN["gate-codeql.yml<br/>Full CodeQL scan on main"]
    C["alert-codeql.yml<br/>Read the published CodeQL findings"]
    V["alert-vulnerability.yml<br/>Read open Dependabot vulnerabilities"]
    M["alert-malware.yml<br/>Read open malware-classified alerts"]
    P["security-alerts action<br/>RoboCop groups findings into GitHub Project tickets"]
    MIDNIGHT --> SCAN
    MIDNIGHT --> V
    MIDNIGHT --> M
    SCAN -->|"Scheduled scan succeeds"| C
    C & V & M --> P
```

The [vulnerability](alert-vulnerability.yml) and [malware](alert-malware.yml)
alert workflows run daily at midnight Pacific (America/Los_Angeles). The
[CodeQL alert workflow](alert-codeql.yml) follows a successful scheduled CodeQL
scan on main. All three alert workflows support manual dispatch. Incomplete
source/model evidence fails before lifecycle writes; verified closure and Project
recovery preserve their independent credential boundaries. These three workflows read existing findings.

The separate CodeQL Gate scans changed languages in PR CI. Its daily and manual
runs perform full analysis.

### Promotion, release and manual operations

```mermaid
flowchart TD
    MAIN["Reviewed source on main"]
    PROMOTE["Promotion PR from main to env-prod"]
    PUSH["Merge updates env-prod"]
    MANUAL["Manual dispatch · retry deployment<br/>Select the existing env-prod branch"]
    APP["ci-deploy.yml<br/>Notoli and MacroMapper release their frontend and backend"]
    INFRA["deploy-gateway.yml<br/>Infrastructure updates the shared gateway"]
    MAIN --> PROMOTE --> PUSH
    PUSH & MANUAL --> APP & INFRA
```

Promote exact reviewed main source through existing `env-prod` controls. Keep
independent app/gateway transactions, immutable digests, private recovery sets,
locks and explicit data-generation barriers. Compare the entire promotion diff
and independently verify running identity, routes, auth and sanitized logs.
Readiness is not authenticated/mail acceptance. Never restore older SQLite data
over newer committed writes or assume migrations can be reversed. App releases
never recreate shared ingress/networks or prune the host. Docs/workflow-only changes
need no unnecessary restart. FullStackTemplate has no active production target;
its onboarding examples do not authorize new resources or an `env-prod` branch.

### Maintaining the architecture

When editing a workflow, review its triggers, job dependencies, permissions,
and trust boundaries. Update the diagrams when those relationships change.

## 🧪 Coverage boundaries

Action-local regressions cover reviewer publishing, security-alert lifecycle,
dependency evidence and workflow permission and pin policy under their existing
gates. App repositories retain backend, frontend/browser and shared
release suites; the canonical release tests remain in Infrastructure `app-release/v1`.
Root tooling, gateway/ingress, SQLite snapshot and release-profile suites were
removed at the owner's request. Their former coverage is not provided by the
remaining checks. Mocked/local evidence does not establish live reviewer loading,
authenticated production journeys, recovery acceptance, physical-device behavior,
email receipt or paid AI behavior. Use disposable fixtures and separately authorized
runtime verification for those claims.

### Locked repository Python tooling

The root `pyproject.toml` declares a non-packaged Python 3.12 tooling project;
`uv.lock` records the complete PyYAML graph. Run `uv sync --locked` and use
`uv run --locked` for local checks. The local `setup-uv` action bootstraps uv
0.13.8, synchronizes the same lockfile and exposes its Python to Node subprocesses.
Dependabot uses the `uv` ecosystem at `/` with the existing weekly cadence.
Production hosts still run ordinary Python release/gateway scripts and do not
need uv or this developer environment.

Changes to package manifests or the locked dependency graph go through normal PR review.
Dependency Review checks supported dependencies for known advisories. The locked
graph provides reproducibility. Docker image advisories and live operations keep
their separate operator acceptance.

Dependabot's `uv` updater reads `pyproject.toml` and `uv.lock`; a requirements
export is unnecessary. Runtime and development dependencies retain the existing
reviewer and independent-check policy. The source diff includes every lockfile;
only the separate dependency-usage search omits generated lockfile matches.
The uv executable is a deliberately pinned toolchain bootstrap in `setup-uv`
and application Dockerfiles; package dependency PRs do not change that bootstrap.
Review and synchronize its version and CI wheel hash separately when upgrading
the toolchain; see the [verified bootstrap contract](../actions/README.md#-python-toolchain-bootstrap).
Hosted version/security update acceptance still requires a fresh Dependabot run
after the reviewed configuration reaches main.
