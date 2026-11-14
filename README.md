# 🏗️ Jude Andrew Alaba Infrastructure

**Shared hosting infrastructure for independent applications**

This repository provides the Docker ingress, Nginx routing, and versioned
release standard for applications on `judeandrewalaba.com`, including Notoli
and MacroMapper. Each application owns its own backend, data, and releases.

## ✨ Features

- Shared HTTPS ingress and application routing.
- Independent application releases with pinned common tooling.
- Explicit verification and recovery procedures.
- Application onboarding and optional MCP routing.
- Automated validation, security checks, and AI reviews.

## 🚀 Tech stack

- **Routing and hosting:** Nginx, Docker Compose, Cloudflare, and DigitalOcean.
- **Release tooling:** Python and shell scripts.
- **Automation:** GitHub Actions.

## 📚 Documentation

- [Gateway and routing](nginx/README.md) — configuration and routing ownership.
- [Application release standard](app-release/README.md) — shared release tooling.
- [GitHub setup and workflows](.github/README-WORKFLOWS.md) — configuration and automation.
- [Contributing](CONTRIBUTING.md) — contribution and review expectations.
- [Changelog](CHANGELOG.md) — project updates.

## 📜 License

[Modified MIT License (Non-Commercial Use Only)](LICENSE.md).
Commercial use requires separate permission from the copyright holder.
