# ⚙️ JudeAndrewAlabaInfrastructure GitHub workflows

This folder owns GitHub Actions, dependency updates, AI reviews, and
security-alert automation for this repository.

## 🚦 Before your first pull request

Complete the [GitHub setup checklist](GITHUB_SETUP.md) before expecting all
required workflows to pass. It covers repository settings, reviewer Apps,
Actions and Dependabot credentials, the GitHub Project, and branch protection.
Repository settings and secret values are configured separately from source.

## 🧭 Structure

- `workflows/`: CI, review, security-alert, and release entry points.
- `actions/`: reusable local actions and regression tests.
- `dependabot.yml`: dependency update configuration.
- [Workflow reference](WORKFLOW-REFERENCE.md): exact triggers, gates, and credential contracts.
- [Reviewer guide](AI-REVIEWERS.md): review context, feedback, and recovery.

## 🔄 Pull requests and releases

Pull requests run the applicable validation and security checks plus the
required AI reviews. Missing required credentials and unavailable reviewer
results remain visible failures. Forks retain their credential isolation.

Gateway promotion, owner authorization, and rollback follow the
[gateway release guide](../docs/gateway-releases.md). CI success does not
authorize merging or production operations.

## 🧪 Checks and diagnostics

See the [repository test guide](../tests/README.md) for local commands and
prerequisites. The [CI/CD architecture](../docs/CI-CD-ARCHITECTURE.md) maps
workflow events and trust boundaries.

## 📚 Detailed workflow reference


<details>
<summary>Triggers, checks, credentials, and maintenance contracts</summary>

<a id="major-upgrade-review-evidence"></a>

- [Major-upgrade review evidence](WORKFLOW-REFERENCE.md#major-upgrade-review-evidence)

<a id="-applicable-parity"></a>

- [🧭 Applicable parity](WORKFLOW-REFERENCE.md#-applicable-parity)

<a id="-required-checks-and-permissions"></a>

- [🔒 Required checks and permissions](WORKFLOW-REFERENCE.md#-required-checks-and-permissions)

<a id="-gateway-release-workflow"></a>

- [🚦 Gateway release workflow](WORKFLOW-REFERENCE.md#-gateway-release-workflow)

<a id="-validation-and-activation"></a>

- [🧪 Validation and activation](WORKFLOW-REFERENCE.md#-validation-and-activation)

<a id="-separate-openai-reviewer-credentials"></a>

- [🔑 Separate OpenAI reviewer credentials](WORKFLOW-REFERENCE.md#-separate-openai-reviewer-credentials)

<a id="-ai-reviewer-parity-across-repositories"></a>

- [🔄 AI reviewer parity across repositories](WORKFLOW-REFERENCE.md#-ai-reviewer-parity-across-repositories)

<a id="-dependency-evidence-and-alert-lifecycle-parity"></a>

- [🛡️ Dependency evidence and alert lifecycle parity](WORKFLOW-REFERENCE.md#-dependency-evidence-and-alert-lifecycle-parity)

<a id="-reviewer-model"></a>

- [🤖 Reviewer model](WORKFLOW-REFERENCE.md#-reviewer-model)

<a id="-compatible-codeql-updates"></a>

- [📦 Compatible CodeQL updates](WORKFLOW-REFERENCE.md#-compatible-codeql-updates)

<a id="-atomic-codeql-regression-guard"></a>

- [🧪 Atomic CodeQL regression guard](WORKFLOW-REFERENCE.md#-atomic-codeql-regression-guard)

<a id="security-alert-recovery"></a>

- [Security-alert recovery](WORKFLOW-REFERENCE.md#security-alert-recovery)

<a id="-batch-2-workflow-supply-chain"></a>

- [🔒 Batch 2 workflow supply chain](WORKFLOW-REFERENCE.md#-batch-2-workflow-supply-chain)

<a id="-automation-regressions-and-bounded-diagnostics"></a>

- [🧪 Automation regressions and bounded diagnostics](WORKFLOW-REFERENCE.md#-automation-regressions-and-bounded-diagnostics)

<a id="reviewer-context-follow-ups-and-usage"></a>

- [Reviewer context, follow-ups and usage](WORKFLOW-REFERENCE.md#reviewer-context-follow-ups-and-usage)

<a id="architecture-and-production-summaries"></a>

- [Architecture and production summaries](WORKFLOW-REFERENCE.md#architecture-and-production-summaries)

<a id="security-alert-configuration-contract"></a>

- [Security-alert configuration contract](WORKFLOW-REFERENCE.md#security-alert-configuration-contract)

<a id="-retired-agent-cleanup"></a>

- [🧹 Retired agent cleanup](WORKFLOW-REFERENCE.md#-retired-agent-cleanup)

<a id="-locally-runnable-reporting-helpers"></a>

- [🧪 Locally runnable reporting helpers](WORKFLOW-REFERENCE.md#-locally-runnable-reporting-helpers)

</details>
