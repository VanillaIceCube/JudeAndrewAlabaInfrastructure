# 🛠️ Working in this repository

This repository owns shared ingress and the versioned application release
standard. Read [README.md](README.md), the [architecture](docs/architecture-v2.md)
and the [release standard](docs/app-release-standard.md) before related changes.

- Keep app releases independent. Preserve existing network objects, exact Notoli
  proxy trust, immutable images, SQLite journal recovery and explicit rollback.
- Update the relevant guide and [CHANGELOG.md](CHANGELOG.md) when behavior,
  configuration or operator steps change. Use concise emoji-prefixed headings
  consistent with the neighboring application repositories.
- Change common release code under `app-release/v1`, regenerate its manifest,
  then synchronize both app PRs to the same commit. Do not edit vendored copies
  independently. App configuration and Compose remain app-specific.
- Validate Compose and run `python -m unittest discover -s tests -v` against a
  disposable local/CI Docker daemon. Also run
  `python scripts/update_release_manifest.py --check`; shared behavior changes
  require both applications' deployment suites and parity checks.
- Follow [CONTRIBUTING.md](CONTRIBUTING.md) for review and validation. Never run
  the production cutover guide as a test or expose private recovery/env/key data.

Owner decisions are recorded on [issue #4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4).
Architecture approval does not authorize merging, release-branch promotion or
production operations. Use issue #4 for the designated operator and exact
production authorization; do not infer either from source approval. Repository automation in issues #5–#9 is owner-prioritized; follow the
[workflow guide](.github/README-WORKFLOWS.md). Implementation approval still
does not authorize merging or production operations.

## 🚀 Gateway promotion authorization

The owner's [October 19 decision](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4#issuecomment-6273538610)
authorizes automatic gateway deployment when the owner promotes reviewed main
source to `env-prod`. The owner-triggered promotion is production authorization;
no second reviewer or per-release approval variable is required. Manual retries
must also be owner-triggered. Initial host setup and explicit gateway recovery
retain their separately authorized operator scope. Application release rules
and the one-time cutover are unchanged.

## Jules recurring agents

Nora and Marty use the [v3 operating rules](.jules/README.md): at most one open
PR per agent per repository. Repeat runs maintain the existing PR, integrate
current main, and verify its latest head instead of opening another PR.

## 🔑 OpenAI reviewer isolation

Use `OBI_WAN_OPENAI_API_KEY`, `LINT_EASTWOOD_OPENAI_API_KEY`, and
`ROBOCOP_OPENAI_API_KEY` for their respective reviewers; RoboCop also owns
all security-alert model calls. `OPENAI_REVIEWERS_PROJECT_ID` identifies this repository's
reviewer project. Keep credentials separate across repositories and application
environments, preserve visible missing-key failures, and follow the deferred
cutover steps in `.github/README-WORKFLOWS.md`.
