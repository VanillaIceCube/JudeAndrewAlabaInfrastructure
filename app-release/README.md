# 📦 Application release standard

This folder owns the versioned release implementation consumed by application
repositories. Each application retains its own configuration, services,
database, and production authorization.

## 🧭 Structure

`v1/` contains the canonical release implementation, tests, workflow template,
parity checker, and manifest. `update_release_manifest.py` maintains that
manifest from outside the versioned consumer source. The
[release standard](../docs/app-release-standard.md) documents the contract and
consumer-specific differences, including template onboarding.

## 🧰 Maintenance

Update common code here before synchronizing consumers. Regenerate its
manifest with `python app-release/update_release_manifest.py`, then verify with
`python app-release/update_release_manifest.py --check` from the repository root.
Follow the release standard's pinned-source update procedure; documentation
changes do not justify editing a vendored consumer independently.

## 🧪 Checks

The canonical suites remain in `v1/tests/` and run through consumer application
deployment suites with their app policies. Follow the release standard's parity
checks and test on disposable fixtures. Infrastructure's root release-profile
matrix has been retired; the manifest check remains in Infrastructure CI.

## 📚 Further reading

- [Architecture and application ownership](../docs/architecture-v2.md).
- [Application onboarding](../docs/onboarding.md).
