# 🔑 Review and security setup

## 🤖 Identity and credentials

Existing account installations include this repository. Obi-Wan App `4276219`,
Lint Eastwood `4271110` and RoboCop `4271112` mint short-lived tokens scoped to
Infrastructure. Review tokens request contents read and pull requests write.
RoboCop alerts request issues write and only the relevant alert API read permission.
Metadata read is implicit. Lint Eastwood's existing account write capability is
narrowed without changing other repositories. Bots never edit, merge or deploy.

| Configuration | Storage/purpose |
| --- | --- |
| `OBI_WAN_CODE_NOBI_APP_ID`, `LINT_EASTWOOD_APP_ID`, `ROBOCOP_APP_ID` | Actions variables for identities |
| Corresponding `*_PRIVATE_KEY` | Actions secrets for App authentication |
| `OPENAI_PROJECT_ID` | Existing review project variable |
| `OPENAI_API_KEY` | Infrastructure-only restricted Responses write key, Actions secret |
| `SECURITY_ALERTS_PROJECT_ID` | Project #13 variable: `PVT_kwHOAYDAa84BmitT` |
| `SECURITY_ALERTS_TOKEN` | Separate Project v2 read/write secret, never used for issue/alert APIs |

Prefer expiring fine-grained account Projects read/write credentials, or classic
`project` scope if unsupported. Record expiry and rotate before expiration.
No Dependabot secrets are required. Keep review keys separate from production
app/SSH/environment credentials; no values enter tickets, logs or artifacts.

## 🛡️ Repository and Project settings

Enable dependency graph, Dependabot alerts/security-update PRs, secret scanning
and push protection where available. Keep `allow_auto_merge=false`. CodeQL uses
advanced Actions setup, not an overlapping default setup. Security-update PR
creation never authorizes merging.

Project #13 uses Status (Backlog/Done), Domain (CI/CD), Work type (Security),
Priority (P1/P2), Size (M) and numeric Estimate. End date is optional. Reused
items retain human planning fields. Existing labels: `codeql`, `vulnerability`,
`malware`, `dependencies`, `github_actions`, `docker`. Validate Project
access/schema before issue writes; RoboCop alone mutates issues.

Require `CI / Required CI` after its first green run using the owner's review
policy. Do not weaken protections to accept a PR.

## ✅ Acceptance

Verify green independent gates and native reviews from
`obi-wan-code-nobi-reviewer[bot]`, `lint-eastwood-build-sheriff[bot]` and
`robocop-security-officer[bot]`, all three SARIF categories, alert API access and
Project #13 credential access. Publisher tests cover valid lines, duplicates,
blocking findings and unavailable output; do not invent an inline finding.

After owner merge, verify the default-branch baseline, manually run the three
alert workflows and observe Dependabot's first PR. Keep tickets open for
acceptance evidence still dependent on default-branch activation.
