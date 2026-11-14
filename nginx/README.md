# 🌐 Gateway and routing

This folder owns the shared Nginx gateway configuration. Applications retain
their own backends, databases, OAuth providers, and independent releases.

## 🧭 Structure

See the [ingress architecture](../docs/architecture-v2.md) for canonical vhosts,
network names, upstreams, forwarded headers, exact proxy trust, and timeouts.
The [Compose definition](../compose.yml) owns the gateway service.

## 🚀 Operations

- [Gateway releases and rollback](../docs/gateway-releases.md).
- [Application onboarding](../docs/onboarding.md).
- [Initial cutover and reversal](../docs/cutover.md).
- [Optional application MCP routing](../docs/optional-mcp.md).

The routing contract includes MacroMapper's 120-second upstream read timeout
and its companion app rollout checks. Follow the designated operations guide
and owner authorization for live changes; configuration documentation is not
an instruction to run a cutover.

## 🧪 Checks

Follow the [test guide](../tests/README.md) on a disposable Docker daemon.
Never use production as a fixture.
