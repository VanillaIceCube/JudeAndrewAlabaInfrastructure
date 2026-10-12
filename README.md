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
| Adding an application | [Onboarding](docs/onboarding.md) |
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
