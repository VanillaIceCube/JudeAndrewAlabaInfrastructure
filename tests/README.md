# 🧪 JudeAndrewAlabaInfrastructure tests

This folder owns repository-tooling regressions. Application-specific tests
remain beside their backend and frontend code.

## 🧭 Suites

| Suite | Location |
| --- | --- |
| Bounded diagnostic logs | `tests/bounded-log.test.cjs` |
| GitHub action regressions | `.github/actions/` |
| Gateway routing, ingress, retirement, and release profiles | `tests/test_*.py` |
| Shared release implementation | `app-release/v1/tests/` and the consumer app suites |

## 💻 Run checks

Use Python 3.12+, Node.js, Docker Engine/Compose, and OpenSSL with a disposable
local or CI daemon. From the repository root:

```sh
docker compose -f compose.yml config --quiet
python scripts/update_release_manifest.py --check
python -m unittest discover -s tests -v
node --test tests/*.test.cjs .github/actions/*/*.test.js
```

## 🐳 Isolation and shared release changes

Tests use temporary certificates, unique networks, containers, and loopback
ports. They do not execute the production cutover procedure. Common release
changes also require both consumer app suites and pinned-source parity checks.
Run Actionlint and ShellCheck through `scripts/lint_infrastructure.sh` for
automation changes. See [contributing](../CONTRIBUTING.md).

## 📚 Further reading

- [Automation coverage](README.md#-coverage-and-limitations).
- [Workflow reference](../.github/WORKFLOW-REFERENCE.md).
- [Repository scripts](../scripts/README.md).

## 🔍 Coverage and limitations

Run the relevant unit, integration, and configuration checks for changed code.
Review exact test/check results rather than treating a source match or issue
status as acceptance. Configuration validation does not deploy services.
Use disposable fixtures for Docker and browser tests; keep real user data,
credentials, mail delivery, paid model calls, and production recovery outside
those fixtures. Mocked provider tests do not prove live delivery or billing.
Current CI requirements and diagnostic retention belong to the
[workflow reference](../.github/WORKFLOW-REFERENCE.md).
