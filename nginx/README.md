# 🌐 Gateway and routing

This folder owns the shared Nginx gateway configuration. Applications retain
their own backends, databases, OAuth providers, and independent releases.

## 🧭 Structure

See the [ingress architecture](../docs/architecture-v2.md) for canonical vhosts,
network names, upstreams, forwarded headers, exact proxy trust, and timeouts.
The [Compose definition](../compose.yml) owns the gateway service.
`gateway_release.py` owns authorized release/recovery transactions;
`gateway_transport.py` verifies promotion authorization before loading credentials
and transports immutable inputs from Actions; `check_host.py` verifies topology
without provisioning or repair.

## 🚀 Operations

- [Gateway releases and rollback](../docs/gateway-releases.md).
- [Application onboarding](../docs/onboarding.md).
- [Initial cutover and reversal](../docs/cutover.md).
- [Optional application MCP routing](../docs/optional-mcp.md).

The routing contract includes MacroMapper's 120-second upstream read timeout
and its companion app rollout checks. Follow the designated operations guide
and owner authorization for live changes; configuration documentation is not
an instruction to run a cutover.

Run documented commands from the repository root. The gateway workflow invokes
`python nginx/gateway_transport.py authorize` before credential loading, then the
transport command. For authorized operator adoption or explicit rollback, follow
the release guide's `python nginx/gateway_release.py` commands and exact source
identities. Cutover preflight uses `python nginx/check_host.py <legacy|vacant|host>`;
read the designated procedure before choosing a phase.

## 🧪 Checks

See [workflow checks](../.github/workflows/README.md#-checks-and-diagnostics).
CI validates Compose configuration; the root routing, gateway transaction and
retirement suites have been retired. Runtime and recovery acceptance remain
separately authorized operations. Never use production as a fixture.
