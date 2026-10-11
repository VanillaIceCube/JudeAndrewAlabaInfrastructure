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
production authorization; do not infer either from source approval. Advanced repository automation in issues #5–#9 remains deferred.
