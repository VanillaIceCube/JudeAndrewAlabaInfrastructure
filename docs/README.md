# 📚 JudeAndrewAlabaInfrastructure documentation

Use the folder READMEs for everyday work. These references explain architecture,
integration contracts, maintenance, and recorded verification.

## 🧭 Start here

- [Gateway and routing](../nginx/README.md).
- [Application release standard](../app-release/README.md).
- [GitHub setup and workflows](../.github/README-WORKFLOWS.md).
- [Scripts](../scripts/README.md).
- [Tests](../tests/README.md).

## 🚀 Deployment and operations

- [Application onboarding](onboarding.md).
- [Gateway releases and rollback](gateway-releases.md).
- [Initial cutover and reversal](cutover.md).
- [Optional MCP ingress](optional-mcp.md).

[Issue #4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4)
records owner decisions and the exact authorization for production work.
Architecture or CI approval alone does not authorize merging or deployment.

## 🧱 Product and architecture

- [Shared application release standard](app-release-standard.md).
- [Shared ingress contract v2](architecture-v2.md).
- [CI/CD architecture and trust boundaries](CI-CD-ARCHITECTURE.md).

## 🧰 Maintenance and integration

- [Automation coverage and failure diagnostics](AUTOMATION-COVERAGE.md).

## 🗂️ Verification and history

- [Batch 3 shared capability parity](BATCH3-PARITY.md).
- [Retire the external YNAB integration and shared MCP issuer](mcp-retirement.md).
