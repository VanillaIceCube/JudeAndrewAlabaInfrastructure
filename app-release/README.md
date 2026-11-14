# 📦 Application release standard

This folder owns the versioned release implementation consumed by application
repositories. Each application retains its own configuration, services,
database, and production authorization.

## 🧭 Structure

`v1/` contains the canonical release implementation, tests, workflow template,
parity checker, and manifest. The
[release standard](REFERENCE.md) documents the contract and
consumer-specific differences, including template onboarding.

## 🧰 Maintenance

Update common code here before synchronizing consumers. Regenerate its
manifest with `python scripts/update_release_manifest.py`, then verify with
`python scripts/update_release_manifest.py --check` from the repository root.
Follow the release standard's pinned-source update procedure; documentation
changes do not justify editing a vendored consumer independently.

## 🧪 Checks

See [repository tests](../tests/README.md), the consumer application deployment
suites, and the release standard's parity checks. Test on disposable fixtures.

## 📚 Further reading

- [Architecture and application ownership](../nginx/ARCHITECTURE.md).
- [Application onboarding](../nginx/ONBOARDING.md).
- [Contributing](../CONTRIBUTING.md).
