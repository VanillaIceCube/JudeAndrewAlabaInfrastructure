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
| Package malware | Explicitly inapplicable without manifests; adding a manifest blocks until scanner support is reviewed |
| Secrets | Gitleaks on PRs plus repository secret scanning and push protection |
| Dependabot | Weekly grouped Actions and separate Compose updates, limits, owner assignment and existing labels |
| Security alerts | Daily/manual CodeQL, all-severity vulnerabilities and advisory-classified malware, RoboCop issues and Project #13 metadata |

CodeQL/Dependency Review do not scan Nginx configuration or image contents for
malware/CVEs. Disposable Nginx tests cover actual routing, DNS, forwarding/trust,
logging and reversal. Image updates require separate operator-reviewed
image/advisory assessment and production authorization.

## 🔒 Required checks and permissions

`CI / Required CI` requires independent gates and all applicable reviews.
Failed/cancelled/unexpectedly skipped checks block it. REQUEST_CHANGES,
unavailable AI output and diff overflow fail reviewer checks. Inline placement,
prior-history and duplicate suppression are tested. Bot approval never
authorizes merging or deployment.

Fork and Dependabot PRs run independent read-only gates; secret-dependent AI
reviews are explicitly inapplicable. No Dependabot App secrets or
`pull_request_target` workflow exist. Same-repository human PRs require the
three reviewers. The reusable major-upgrade collector remains available for
separately authorized trusted review runs. Dependabot requires manual owner merge.

GITHUB_TOKEN begins with contents read. Only CodeQL upload/review jobs request
additional permissions. App tokens name this repository and explicit permissions;
Lint Eastwood receives contents read despite its existing broader account
installation. Checkout does not persist credentials. No workflow requests
contents write, commits fixes, merges or deploys.

Alerts serialize each feed, validate every source ref exactly once, and manage
only `infrastructure-security-alert` issues. Missing credentials, unavailable
feeds, malformed AI JSON or absent Project metadata fail visibly. Source links
remain; secret and private host/recovery contents are excluded.

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
while enforcing original exit status. Shared release files/manifest are unchanged.

See [setup](GITHUB_SETUP.md). Default-branch Dependabot/schedules activate after
owner merge. The unmerged feature PR proves checks and identities, not scheduled
activation. No merge, promotion or production operation is implied.
