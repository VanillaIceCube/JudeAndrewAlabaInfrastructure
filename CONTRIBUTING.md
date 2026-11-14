# 🤝 Contributing

Open a scoped PR against `main`. Describe the resulting behavior, validation and
any operational impact. Shared decisions belong in
[issue #4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4);
keep app implementation work in its app repository.

## 🧪 Local validation

Use Python 3.12+, Docker Engine/Compose, and OpenSSL on a disposable workstation
or CI daemon. Run from the repository root:

```sh
docker compose -f compose.yml config --quiet
python scripts/update_release_manifest.py --check
python -m unittest discover -s tests -v
node --test .github/actions/*/*.test.js
```

Tests create uniquely named temporary containers/networks and local fixture
certificates. They never execute the production runbook. Changes to the common
release implementation also require both apps' tests and
[parity verification](docs/app-release-standard.md#-automated-parity-and-updates).

## 📚 Documentation and review

Automation changes also run actionlint and ShellCheck through
[`scripts/lint_infrastructure.sh`](scripts/lint_infrastructure.sh). See the
[workflow guide](.github/README-WORKFLOWS.md) for events, evidence and permissions.

Keep the README, relevant operational guide and changelog current. Use
`Added`, `Fixed`, `Changed`, `Removed` changelog groups as needed, matching the
application repositories. Keep coordination history in issues rather than new
PR-specific source documents. Never commit credentials, real certificates,
database files or private recovery artifacts.

The owner approves each PR merge and production plan separately. Passing tests
or a reviewer verdict does not authorize a merge or live operation. Follow the
[license](LICENSE.md) when copying or distributing this project.
