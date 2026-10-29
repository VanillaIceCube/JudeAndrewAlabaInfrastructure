# 🏗️ Jude Andrew Alaba Infrastructure

Shared Docker ingress, Nginx routing and the versioned application release
standard for `judeandrewalaba.com` applications.

## 🧭 Architecture

The [owner-approved v2 architecture](docs/architecture-v2.md) separates the
host-owned gateway from independent Notoli and MacroMapper releases. Existing
Docker networks, certificate paths and Notoli's exact trusted proxy remain
preserved through the reviewed migration.

## 📦 What's here

| Area | Source / guide |
| --- | --- |
| Host ingress | [Compose](compose.yml), [Nginx](nginx/nginx.conf) |
| Application releases | [Shared standard and parity matrix](docs/app-release-standard.md), [versioned source](app-release/v1) |
| Production operations | [Cutover and reversal](docs/cutover.md) |
| Subsequent gateway releases | [Promotion, approval and rollback](docs/gateway-releases.md) |
| Adding an application | [Onboarding](docs/onboarding.md) |
| YNAB MCP investigation | [Gateway decision and disposable proof](docs/ynab-mcp.md) — production blocked |
| YNAB stdio runtime | [Pinned, inactive runtime and container tests](services/ynab-mcp/README.md) |
| YNAB HTTP gateway | [Inactive owner-authenticated proxy and acceptance](services/ynab-gateway/README.md) |
| YNAB network/ingress | [Inactive route, controlled egress and DNS/TLS plan](docs/ynab-ingress.md) |
| Development | [Contributing](CONTRIBUTING.md), [agent guidance](AGENTS.md) |
| Repository automation | [Checks and reviewers](.github/README-WORKFLOWS.md), [setup](.github/GITHUB_SETUP.md) |
| Project history | [Changelog](CHANGELOG.md) |

## 🧪 Validation

Run against a disposable local/CI Docker daemon:

```sh
docker compose -f compose.yml config --quiet
python scripts/update_release_manifest.py --check
python -m unittest discover -s tests -v
```

The tests use temporary fixture certificates, unique networks and loopback
ports. They do not invoke the production runbook. Common release changes also
run the same deployment/recovery suites and pinned-source parity gate in both
application repositories.

## ⏱️ MacroMapper estimation timeout

MacroMapper's backend routes use a 120-second upstream read timeout. Release
this gateway setting before the companion MacroMapper app change for
[meal-estimation incident #245](https://github.com/VanillaIceCube/MacroMapper/issues/245).
The app enforces a 110-second total AI budget with no SDK retries and uses
threaded request handling. See the [routing contract](docs/architecture-v2.md)
for rollout checks and the [app release guide](https://github.com/VanillaIceCube/MacroMapper/blob/main/deploy/production/README.md).

## 🚦 Coordination

[Issue #4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4)
records owner decisions and PR/rollout status. Architecture approval does not
authorize a merge or deployment; the host operator needs separate approval for
the exact production plan. This repository owns shared ingress; the runbook
transfers legacy ingress only within that approved plan. Consult #4 for live status.
Issues #5–#9 track the owner-prioritized automation implementation and acceptance.
CI and reviewer approval never authorize automatic merging or production operations.

## 📜 License

[Modified MIT License (Non-Commercial Use Only)](LICENSE.md), matching the owner's
application/template repositories. See the license for terms and commercial
licensing contact.

The release standard also supports template onboarding through an explicit app
policy and disposable profile fixtures; see [template adoption](docs/app-release-standard.md#-template-adoption).

## 🔑 AI reviewer credentials

Obi-Wan, Lint Eastwood, and RoboCop use separate OpenAI keys scoped to this
repository. See the [workflow setup and deferred migration](.github/README-WORKFLOWS.md#-separate-openai-reviewer-credentials)
for exact secret names, project configuration, verification, and rollback.

Trusted same-repository Dependabot PRs receive all three AI reviews, matching
MacroMapper, Notoli and FullStackTemplate. Forks stay excluded. See the
[parity contract](.github/README-WORKFLOWS.md#-ai-reviewer-parity-across-repositories)
and provision all six reviewer secrets in both Actions and Dependabot. Owner
merge approval remains mandatory.


## 🔌 Optional MCP applications

Follow the [optional MCP contract](docs/optional-mcp.md) for app-owned ASGI/OAuth, shared ingress, readiness and rollback. Notoli remains enabled; MacroMapper is not advertised until its application registry is ready. Preserve independent releases and exact app proxy trust.
