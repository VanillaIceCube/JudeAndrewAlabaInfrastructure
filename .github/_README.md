# ⚙️ GitHub automation

GitHub Actions, repository setup, dependency updates, and AI reviews for infrastructure.
Source-controlled configuration and GitHub account/repository settings are separate.

## 🧭 Structure

| Location | Purpose |
| --- | --- |
| [workflows](workflows/README.md) | Entry points, gates, reviewers, schedules and deployment. The guide includes four flow diagrams. |
| [scripts](scripts) | Standalone automation programs that workflows or people run, and their supporting modules. |
| [actions](actions/README.md) | Reusable composite steps, each with its own `action.yml` and implementation. |
| [tests](tests) | One suite per tested JavaScript implementation or workflow, named after its source. |
| [tests/fixtures](tests/fixtures) | Saved test inputs and expected output. Use lowercase, hyphen-separated nouns for the data and add the scenario last when variants exist. |
| [package.json](package.json) and [package-lock.json](package-lock.json) | JavaScript dependencies for automation and their verified install versions. |
| [dependabot.yml](dependabot.yml) | Dependency ecosystems and update schedules. |

Keep the exact `pyyaml` development pin lowercase so Dependabot's uv updater can match it.

<a id="-ci-tools"></a>

### CI tools

Install Node.js and run `npm ci --prefix .github --ignore-scripts --no-audit --no-fund` from the repository root for the automation checks. Run `uv sync --locked` for the Python release tooling.
The workflows define lint checks, bounded review logs and the Required CI result. See the
[workflow checks](workflows/README.md#-checks-and-diagnostics) for local commands.

## 🚦 Before your first pull request

1. Configure Actions, dependency alerts, advanced CodeQL, and available secret scanning/push protection using this repository's settings below.
2. Install the three reviewer GitHub Apps and set their App ID variables.
3. Store each persona's OpenAI key and App private key in both Actions and Dependabot secrets: six reviewer secrets in each store.
4. Configure this repository's OpenAI reviewer project and native issue fields. To group alert tickets under an existing tracking issue, set the optional repository Actions variable `ROBOCOP_PARENT_ISSUE` to its issue number.
5. Verify fresh same-repository human and Dependabot PR results before activating or changing required checks.
6. Configure deployment separately through the app or gateway production guide.

Missing credentials and unavailable review evidence fail visibly. Existing secret
values are not recoverable from GitHub; use the original credentials through the
owner's approved process. Never weaken checks to make setup pass.

## ⚙️ Repository setup

<a id="-identity-and-credentials"></a>

### Identity and credentials

Existing account installations include this repository. Obi-Wan App `4276219`,
Lint Eastwood `4271110` and RoboCop `4271112` mint short-lived tokens scoped to
Infrastructure. Review tokens request contents read and pull requests write.
RoboCop alerts request issues write and only the relevant alert API read permission.
Metadata read is implicit. Lint Eastwood's existing account write capability is
narrowed without changing other repositories. The reviewer Apps only review. The default-branch Dependabot policy uses the workflow token.

| Configuration | Storage/purpose |
| --- | --- |
| `OBI_WAN_CODE_NOBI_APP_ID`, `LINT_EASTWOOD_APP_ID`, `ROBOCOP_APP_ID` | Actions variables for identities |
| Corresponding `*_PRIVATE_KEY` | Actions + Dependabot secrets for App authentication |
| `OPENAI_REVIEWERS_PROJECT_ID` | OpenAI reviewer project ID shared by this repository's three reviewer keys |
| `OBI_WAN_OPENAI_API_KEY`, `LINT_EASTWOOD_OPENAI_API_KEY`, `ROBOCOP_OPENAI_API_KEY` | Separate Infrastructure-only reviewer keys, Actions + Dependabot secrets; RoboCop also runs all alert feeds |

Store the three OpenAI keys and three App private keys in both Actions and
Dependabot (six reviewer secrets in each). Keep review keys separate from production
app/SSH/environment credentials; no values enter tickets, logs or artifacts.

<a id="-repository-and-project-settings"></a>

### Repository and native issue settings

Enable dependency graph, Dependabot alerts/security-update PRs, secret scanning
and push protection where available. Enable native auto-merge only after the protected follow-up is installed and required as described below. CodeQL uses
advanced Actions setup, not an overlapping default setup. Security-update PR
creation never authorizes merging.

Use the repository's Issues tab and the owner's [native issue schema](https://github.com/VanillaIceCube/fullstack-template/blob/main/.github/_README.md#1-configure-repository-issue-tracking). Backfill and verify existing managed tickets before switching alert workflows. After merging, run all three alert workflows on main and verify native field retention before removing the old Project credentials or closing the board. Record results in [FullStackTemplate #386](https://github.com/VanillaIceCube/FullStackTemplate/issues/386).

**Native issue cutover verification, November 25, 2026.** Project 13 contained 56 issues. The read-back matched native field values and issue types on 56 issues, including all 9 security-alert tickets (2 open). Issue numbers, state, closure reasons, and closure dates were preserved. Examples include [#7](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/7), [#8](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/8).

Retain the repository's existing security alert labels and access controls.

Require `Required CI` in the CI workflow after its first green run using the owner's review
policy. Do not weaken protections to accept a PR.

<a id="-deferred-openai-migration"></a>

### Deferred OpenAI migration

Follow the [exact key mapping and cutover sequence](_README.md#-credential-ownership). Configure the three new secrets before merging the source change; retain the legacy key until usage and all consumers are verified.

## 🔑 Credential ownership

GitHub App token consumers pin `actions/create-github-app-token` v3.3.0;
the security-alert regression tests assert that exact SHA alongside the existing
credential and permission boundaries. CodeQL init/analyze advance together to
v4.39.1, and the Gitleaks action uses v3.0.0.

The four existing repositories already use the accepted persona-specific
credentials and reviewer projects. The following is an onboarding/operator
reference, not a pending model or credential migration. Configure these names
before activating a new installation; missing keys fail visibly and there is
no fallback to a shared `OPENAI_API_KEY`.

Use a dedicated **JudeAndrewAlabaInfrastructure · AI Reviewers** OpenAI project (or the
repository's existing reviewer-only project). Never share credentials between
repositories. Create three distinct keys with these exact display names:

| OpenAI key display name | GitHub secret | Consumer |
| --- | --- | --- |
| `CI · Obi-Wan · Code Review` | `OBI_WAN_OPENAI_API_KEY` | Obi-Wan PR reviews |
| `CI · Lint Eastwood · Build Review` | `LINT_EASTWOOD_OPENAI_API_KEY` | Lint Eastwood PR reviews |
| `CI · RoboCop · Security Review` | `ROBOCOP_OPENAI_API_KEY` | RoboCop PR reviews and all three scheduled/manual alert feeds |

Add all three keys as **Actions repository secrets** and **Dependabot repository
secrets**, using identical values in both stores for this repository. Also store
`OBI_WAN_CODE_NOBI_PRIVATE_KEY`, `LINT_EASTWOOD_PRIVATE_KEY`, and
`ROBOCOP_PRIVATE_KEY` in both stores: six reviewer secrets per store. GitHub
cannot copy the encrypted values between stores; use the original PEM files
or a separately authorized replacement key. Never overwrite working private
keys with placeholder text. OpenAI placeholder entries are nonfunctional and
must be replaced with this repository's real keys before acceptance.

Keep deployment keys, application secrets, and production
environment credentials out of Dependabot. Repository App ID and
`OPENAI_REVIEWERS_PROJECT_ID` variables remain shared configuration for both
review paths. [GitHub's Dependabot restrictions](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-on-actions)
apply even when a human reruns a Dependabot-triggered workflow.

1. In OpenAI Platform, select the repository's reviewer project, open its API
   keys page, and create the three keys above. Restrict each key to the API
   permissions needed for Responses requests; retain model access and Obi-Wan's
   existing semver-major web-search capability. Choose an expiration under your
   rotation policy and record when replacement is due.
2. In GitHub **Settings → Secrets and variables → Actions → Secrets**, add the
   exact secret names in the table. Each value is the full secret key from its
   matching OpenAI entry, not its display name or key ID. Use Dependabot's
   separate secret settings too where specified above.
3. In **Actions → Variables**, set `OPENAI_REVIEWERS_PROJECT_ID` to that same OpenAI
   project's actual `proj_...` ID. All three keys and the project header must
   match. This variable identifies the OpenAI project for the reviewers.
4. Run a same-repository PR smoke test for all three reviewers. Where supported,
   also verify a Dependabot PR using its separate secret store. After an
   approved merge, manually run CodeQL Alert, Vulnerability Alert, and Malware
   Alert on the default branch and observe their next scheduled runs. Do not
   run production deployment to test reviewer credentials.
5. In OpenAI Usage, filter by the reviewer project and individual API key to
   confirm each persona's attribution. An empty alert feed may make no model
   call; record that outcome rather than assuming usage was verified.
6. For configuration recovery, restore the last accepted persona-specific key/
   project bindings and validated reviewer variables, then rerun the latest head.
   Any source revert must use ordinary protected review and retain its matching
   credential contract. A legacy key used elsewhere is not an active reviewer
   fallback; never copy it into all three persona slots or expose key values.
   This reference does not rotate or provision credentials during Batch 3.

See [OpenAI key security, expiration and usage guidance](https://developers.openai.com/api/docs/guides/production-best-practices#api-keys).

## 🔒 Branch protection

VanillaIceCube owns this personal repository and is its sole collaborator with
merge access as verified on November 24, 2026. Both `main` and `env-prod` require
pull requests. Human source merges and production promotions use the owner
account. The main ruleset requires resolved review threads, Required CI, and
Dependabot Policy. Code-owner review is disabled in that ruleset. Recheck these
settings and collaborator access when granting repository roles.

With native auto-merge disabled, first land the reviewed follow-up on `main` using
the existing owner process. Verify that a successful ordinary PR CI run emits a
successful `Dependabot Policy` check on its exact head under GitHub Actions.
Keep `Required CI` required from GitHub Actions (integration 15368) and add
`Dependabot Policy` from the same integration. Recheck both required contexts
and merge-commit support before the owner enables the repository's native
auto-merge setting. Rerun PR CI on active heads that lack the new policy check.

The setting is repository-wide. The workflow requests native auto-merge only for
verified eligible Dependabot PRs. Other PRs follow the manual owner process.
After activation, verify a real eligible Dependabot run, its three current-head
bot approvals and its policy check. Gateway production promotion is owner-triggered on `env-prod`. [Workflow policy](workflows/README.md#protected-dependabot-auto-merge)

<a id="-verification"></a>

## 🧪 Checks

Verify the current head's independent checks and all three native review identities.
Distinguish synthetic local tests from actual GitHub runner/credential acceptance.
After an authorized merge, verify default-branch baselines and separately review
alert-workflow side effects before fresh manual dispatches. A successful human PR
does not prove access to the separate Dependabot secret store. Source review does
not authorize merging, branch promotion, production deployment, or key rotation.

<a id="-acceptance"></a>

### Acceptance

Verify green independent gates and native reviews from
`obi-wan-code-nobi-reviewer[bot]`, `lint-eastwood-build-sheriff[bot]` and
`robocop-security-officer[bot]`, all three SARIF categories, alert API access and
RoboCop's native issue-field access. Publisher tests cover valid lines, duplicates,
blocking findings and unavailable output; do not invent an inline finding.

After owner merge, verify the default-branch baseline, manually run the three
alert workflows and observe Dependabot's first PR. Keep tickets open for
acceptance evidence still dependent on default-branch activation.

<a id="-dependabot-reviewer-acceptance"></a>

### Dependabot reviewer acceptance

Follow the [six-secret setup and four-repository parity contract](_README.md#-credential-ownership).
Use original GitHub App PEM contents in Dependabot; existing Actions secret
values cannot be retrieved/copied through GitHub. OpenAI placeholder values
must be replaced with real repository-specific keys. Configure the shared App
ID and reviewer project variables, then validate a real Dependabot-triggered
PR after the reviewed source is merged by the owner. All three reviews are
required. The protected follow-up verifies all three approvals for the current Dependabot head.

<a id="-related-guides"></a>

## 📚 Reference

- [Workflow behavior and maintenance](workflows/README.md).
- [Shared action and reviewer contracts](actions/README.md).
- [CI/CD architecture](workflows/README.md#-architecture-and-trust-boundaries).
- [Gateway setup and launches](../gateway/README.md#-operations).

## 🤝 Shared engineering ownership and rollout

Shared CI and releases are maintained in Infrastructure. AgentHub maintains the
reviewers and alert triage. This repository owns its triggers, credentials and
required checks. [Migration tracker](https://github.com/VanillaIceCube/infrastructure/issues/191)

Follow fullstack-template's [canonical shared ownership and rollout policy](https://github.com/VanillaIceCube/fullstack-template/blob/main/.github/_README.md#-shared-engineering-ownership-and-rollout)
for repository applicability, canonical source ownership, downstream acceptance and
[main-first releases](https://github.com/VanillaIceCube/fullstack-template/blob/main/.github/_README.md#main-first-releases).
Preserve app-specific profiles and Infrastructure's separate owner authorization,
Required CI and host operations. A shared parent closes only after required downstream
adoptions are merged and verified or explicitly deferred with owner/tracking/acceptance.
