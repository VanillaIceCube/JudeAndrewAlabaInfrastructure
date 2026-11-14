# 🧰 JudeAndrewAlabaInfrastructure scripts

Repository maintenance helpers live here. Run documented commands from the
repository root with the dependencies required by the relevant guide.

## 🧭 Script index

| Script | Purpose |
| --- | --- |
| [bounded_log.py](bounded_log.py) | Bound reviewer logs while retaining early, failing, and late evidence. |
| [check_ci_result.py](check_ci_result.py) | Check that all required gates and applicable reviews succeeded. |
| [check_dependency_scope.py](check_dependency_scope.py) | Reject unreviewed package-manifest/scanner configurations. |
| [check_host.py](check_host.py) | Read-only host topology preflight; does not provision or repair. |
| [ci_architecture.py](ci_architecture.py) | Validate documented CI contracts and regenerate the source inventory. |
| [ci_report.py](ci_report.py) | Export bounded CI check evidence. |
| [gateway_release.py](gateway_release.py) | Run the authorized Linux gateway release transaction. |
| [gateway_transport.py](gateway_transport.py) | Transport gateway release inputs and sanitized evidence from Actions. |
| [install_actionlint.sh](install_actionlint.sh) | Install the pinned, checksum-verified Linux Actionlint release. |
| [lint_infrastructure.sh](lint_infrastructure.sh) | Run infrastructure syntax, workflow, and configuration validation. |
| [snapshot_sqlite.py](snapshot_sqlite.py) | Capture and integrity-check SQLite for an authorized cutover recovery record. |
| [update_release_manifest.py](update_release_manifest.py) | Regenerate or verify the common release manifest. |

## 🚀 Host operations

Gateway release, transport, host preflight, and SQLite capture helpers follow
the [operations guides](../docs/README.md#-deployment-and-operations).
Read the designated procedure before invoking a host-facing command.

## 📚 Further reading

- [Tests and validation](../tests/README.md).
- [GitHub setup and workflows](../.github/README-WORKFLOWS.md).
- [Documentation index](../docs/README.md).
