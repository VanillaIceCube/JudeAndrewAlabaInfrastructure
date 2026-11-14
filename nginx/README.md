# 🌐 Gateway and routing

This folder owns the shared Nginx gateway configuration. Applications retain
their own backends, databases, OAuth providers, and independent releases.

## 🧭 Structure

See the [ingress architecture](ARCHITECTURE.md) for canonical vhosts,
network names, upstreams, forwarded headers, exact proxy trust, and timeouts.
The [Compose definition](../compose.yml) owns the gateway service.

## 🚀 Operations

- [Gateway releases and rollback](RELEASES.md).
- [Application onboarding](ONBOARDING.md).
- [Initial cutover and reversal](CUTOVER.md).
- [Optional application MCP routing](MCP.md).

The routing contract includes MacroMapper's 120-second upstream read timeout
and its companion app rollout checks. Follow the designated operations guide
and owner authorization for live changes; configuration documentation is not
an instruction to run a cutover.

## 🧪 Checks

Follow the [test guide](../tests/README.md) on a disposable Docker daemon and
the [contribution guide](../CONTRIBUTING.md). Never use production as a fixture.

## 🧹 Retired integrations

The external YNAB service and central MCP issuer were retired under owner
decision [#96](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/96).
Applications own their OAuth providers and MCP tools. Preserve existing
Notoli grants, independent app releases, exact proxy trust, and the reviewed
retired-route behavior. Use the designated release/recovery procedure and
current owner authorization for any host change; old cutover approvals do not
authorize future production operations.
