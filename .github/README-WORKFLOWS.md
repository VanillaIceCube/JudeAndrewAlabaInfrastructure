# 🤖 Infrastructure automation

## 🧭 Applicable parity

Audited FullStackTemplate `6ff053460cb6cd5148258c672a2f80b7ca59bc4d` and
MacroMapper `74314f9b6c3abf2b29488837ca16729499bd9bde` on 2026-10-11.
MacroMapper has newer publisher, prior-review and reconciliation fixes; its
OpenAI adapter and upstream collector match the template. Infrastructure adapts
prompts, evidence, input validation, permissions and Project metadata.

| Capability | Behavior |
| --- | --- |
| Obi-Wan Code-nobi | Infrastructure correctness, maintainability, valid inline comments and prior-review history |
| Lint Eastwood | Interprets actionlint/ShellCheck, Compose, ingress/reversal, SQLite recovery and automation diagnostics; never edits source |
| RoboCop | Interprets authoritative scanner evidence and infrastructure security risks |
| CodeQL | All present Python, automation JavaScript and Actions sources on every PR, main push and weekly/manual runs |
| Dependency Review | New high/critical vulnerable dependencies block PRs; Actions use GitHub's dependency graph |
| Package malware | Exact YNAB gateway hashed Python lock: OSV known advisories/catalogued malware plus PyPI hash/yank verification; all other manifests block pending reviewed scanner support |
| Secrets | Gitleaks on PRs plus repository secret scanning and push protection |
| Dependabot | Weekly grouped Actions and separate Compose updates, limits, owner assignment and existing labels |
| Security alerts | Daily/manual CodeQL, all-severity vulnerabilities and advisory-classified malware, RoboCop issues and Project #13 metadata |

CodeQL/Dependency Review do not scan Nginx configuration or image contents for
malware/CVEs. Disposable Nginx tests cover actual routing, DNS, forwarding/trust,
logging and reversal. Image updates require separate operator-reviewed
image/advisory assessment and production authorization.

The [YNAB gateway dependency gate](../services/ynab-gateway/README.md) executes no
packages and fails closed on metadata errors. Its known-malware coverage does not
establish absence of unknown malware, container vulnerabilities or license/provenance
approval. The reusable scope job has a five-minute bound and remains a Required CI gate.

The validation workflow separately builds/tests the inactive authenticated YNAB
gateway against synthetic stdio/HTTP fixtures with network disabled. Its job has
a ten-minute bound, a seven-minute process limit and exact-run cleanup on EXIT.
Its result/log joins the existing automation evidence for Lint Eastwood; failure
blocks the overall Tests/Required CI result. It publishes no image and loads no
real credentials. See the [gateway contract](../services/ynab-gateway/README.md).

## 🔒 Required checks and permissions

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
evidence. Dependabot still requires manual owner merge; AI review adds no merge
or deployment authority.

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

## 🚦 Gateway release workflow

`deploy-gateway.yml` handles only separately authorized `env-prod` promotions
and explicit manual retries/rollback on that branch. It is disabled until the
repository enable variable, reviewed source/workflow and owner/branch validation
and private host adoption prerequisites are established. It uses separate
production credentials, persistent host transactions, exclusive maintenance
locking and gateway-only recovery. Review/scanner workflows cannot deploy.
Like the Notoli and MacroMapper deployment workflows, an authorized promotion
to `env-prod` starts deployment without a second reviewer or per-release
approval variable. Source PRs still require the normal main-branch checks.
See [gateway releases](../docs/gateway-releases.md) for setup, bounded probes,
relevant-change policy, Actions evidence, interruptions and retention. Gateway SSH
configuration lives only in repository Actions settings; no GitHub Environment
or Deployment API record is required. Repository-wide key exposure and the
reviewed-workflow/write-access boundary are documented in that guide.

## 🧪 Validation and activation

```sh
docker compose -f compose.yml config --quiet
python scripts/update_release_manifest.py --check
python -m unittest discover -s tests -v
node --test .github/actions/*/*.test.js
bash scripts/install_actionlint.sh
PATH="${RUNNER_TEMP:-/tmp}/infrastructure-tools:$PATH" bash scripts/lint_infrastructure.sh
```

Use Node 24, Python 3.12+, Docker, OpenSSL and ShellCheck. The Linux amd64
actionlint installer verifies its pinned checksum. CI captures bounded diagnostics
while enforcing original exit status. Shared release changes require a regenerated manifest and matched consumer pins.

The existing validation job also runs the pinned [YNAB gateway experiment](../docs/ynab-mcp.md)
with a four-minute limit, no application credentials and synthetic API fixtures.
Its output feeds the existing automation result and Required CI. This is protocol
evidence, not production dependency certification or service activation; the
evaluated gateway's high/critical advisories and public OAuth gates remain blocking.
The same job runs the [isolated stdio runtime](../services/ynab-mcp/README.md)
container suite under a five-minute limit. Its source/package parity, fresh
high/critical npm audit and synthetic-secret hardening tests do not publish an
image or grant production approval.

See [setup](GITHUB_SETUP.md). Default-branch Dependabot/schedules activate after
owner merge. The unmerged feature PR proves checks and identities, not scheduled
activation. No merge, promotion or production operation is implied.

The recovery gate also runs `tests/test_release_profiles.py`: all five shared
release suites execute against Notoli, MacroMapper, and the template fixture on
the disposable CI Docker daemon. No live host or application onboarding occurs.

## 🔑 Separate OpenAI reviewer credentials

GitHub App token consumers pin `actions/create-github-app-token` v3.3.0;
the security-alert regression tests assert that exact SHA alongside the existing
credential and permission boundaries. CodeQL init/analyze advance together to
v4.39.1, and the Gitleaks action uses v3.0.0.

Credential provisioning is a separate operator step. Configure the new secrets
and project variable before activating these workflows. Missing keys fail
visibly; there is no fallback to the old shared `OPENAI_API_KEY`.

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

Keep `SECURITY_ALERTS_TOKEN`, deployment keys, application secrets, and production
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
   match. This is an OpenAI project ID; `SECURITY_ALERTS_PROJECT_ID` is a separate
   GitHub Project node ID and stays unchanged. App identity variables/private
   keys and deployment credentials also stay unchanged.
4. Run a same-repository PR smoke test for all three reviewers. Where supported,
   also verify a Dependabot PR using its separate secret store. After an
   approved merge, manually run CodeQL Alert, Vulnerability Alert, and Malware
   Alert on the default branch and observe their next scheduled runs. Do not
   run production deployment to test reviewer credentials.
5. In OpenAI Usage, filter by the reviewer project and individual API key to
   confirm each persona's attribution. An empty alert feed may make no model
   call; record that outcome rather than assuming usage was verified.
6. Stage the new secrets and `OPENAI_REVIEWERS_PROJECT_ID` while leaving the
   legacy `OPENAI_API_KEY` and `OPENAI_PROJECT_ID` unchanged. Existing default-
   branch jobs can continue using the legacy pair until the source is merged.
   Keep old keys valid until every affected consumer has verified the new keys;
   retain any Default-project key still used elsewhere. To reverse the source
   change, revert the workflow change; the retained legacy pair remains usable.
   Do not place a shared legacy key into the three new secret slots or expose
   key values in logs/issues.

See [OpenAI key security, expiration and usage guidance](https://developers.openai.com/api/docs/guides/production-best-practices#api-keys).

## 🔄 AI reviewer parity across repositories

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
| Infrastructure | All three / all three | Actions + Dependabot | Owner merge only; Required CI includes every applicable review |

Independent checks, evidence limits and major-upgrade gaps remain specific to
each repository's actual scanners and dependency ecosystems. Infrastructure
retains its non-mutating lint reviewer, immutable actions, no auto-merge,
repository-scoped App tokens and production credential boundary. Parity of
review eligibility does not copy application deployment or auto-fix behavior.

After owner-approved merge, update or rerun a real same-repository Dependabot PR
using the new default-branch policy; an old run retains its original workflow
revision. Verify the run actually uses the new policy, all three App identities,
required review outcomes, and supported major-upgrade evidence or documented
gaps. A human PR run does not prove access to the Dependabot secret store.

## 🛡️ Dependency evidence and alert lifecycle parity

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
Dependabot updates, all-language CodeQL on every run, `pull-requests: read` for
Dependency Review, immutable actions and the separate secret-scanning gate.
Dependency graph evidence covers supported Actions/Compose dependencies; it is
not an image-content scanner and does not assume backend/frontend directories.
