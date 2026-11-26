# Shared Nginx gateway

The [Compose file](../compose.yml) launches one digest-pinned Nginx container, `host-ingress-proxy`, on ports 80 and 443. Each application releases its own backend and frontend.

<a id="-operations"></a>

## Operations

The owner promotes a reviewed source tree to `env-prod`. The [gateway workflow](../.github/workflows/deploy-gateway.yml) also permits an owner-triggered dispatch on that branch. It requires `DEPLOY_ENABLED=true`, checks the original and retrying actors and the exact source and workflow before loading the SSH key. Repository settings hold the SSH host, port, user, independently verified fingerprint, and private key. [Gateway authorization decision](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/41)

The [transport script](scripts/gateway_transport.py) gives the GitHub token only to the GitHub CLI. SSH reads its key from a private temporary file. The transport uploads the reviewed configuration to a private attempt directory and runs the [host launcher](scripts/gateway_release.py) under the exclusive maintenance lock. The launcher validates the archive and Compose model, pulls the pinned Nginx image if needed, and runs `nginx -t` before starting `proxy`. It verifies the image, certificate mount and route network boundaries. The gateway can start before the apps. An app with only one attached service fails the readiness check. An attached backend and frontend are probed through the origin and public edge.

A failed launch exits nonzero. Inspect the systemd unit `gateway-<commit>-<run>-<attempt>` or the private container logs to identify the failed step. A fresh attempt launches the reviewed configuration again. Gateway deployment has no adoption step, generation journal, automatic restore or rollback operation.

## Host preparation

First-time provisioning requires separate operator authorization. Confirm the designated host operator and approved work in the [owner's authorization record](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4) before creating host paths, networks or credentials. An `env-prod` promotion launches the gateway on the prepared host.

Provision `/opt/host-ingress-deploy` and its `incoming/` directory under the deploying identity with mode 0700. Provision `/var/lib/jude-deploy-locks/maintenance.lock` (0600) in a private directory shared with the app launchers. Verify access to Docker, systemd, the registry image, and the pre-existing external networks. Keep the deployment identity and SSH host fingerprint under operator control.

The origin certificate and key are `origin.pem` and `origin.key`. Compose mounts the host certificate directory read-only. Its first-launch default is `/root/apps/notoli/certs`. A subsequent launch uses the existing read-only certificate mount. The operator may supply `/opt/host-ingress-deploy/origin-ca.pem` as the independent origin trust anchor. Keep key material off GitHub and out of logs.

<a id="-structure-and-ownership"></a>

## Structure and ownership

| External network | Expected subnet | Gateway address and purpose |
| --- | --- | --- |
| `notoli_backend_private` | `172.30.88.0/29` | `172.30.88.2` is the backend’s sole trusted proxy. The backend uses `172.30.88.3`. |
| `notoli_default` | `172.18.0.0/16` | Notoli frontend traffic |
| `macromapper-ingress` | `172.20.0.0/16` | `172.20.0.3` is MacroMapper’s trusted proxy. |

The [vhosts](nginx/vhosts/) route browser requests to the matching frontend and API, authentication and discovery requests to the matching backend. [Header configuration](nginx/headers.conf) overwrites forwarded client and scheme headers. [TLS configuration](nginx/tls.conf) uses the operator’s origin certificates. Backend services have no host-published port. Adding an app requires reviewing its exact routes, hostnames, network membership, trust boundaries, resource capacity and independent deployment.

<a id="-optional-mcp-contract"></a>

## Optional MCP contract

Preserve the app-owned issuer, exact `/mcp` path, discovery URLs, consent and token routes, and private cache rules. Frontend consent remains in the trusted top-level window. Check matching Cloudflare DNS, TLS, Redirect, WAF and caching settings when routing changes. Infrastructure owns no user accounts, client grants or product actions.

## Checks

```sh
docker compose config --quiet
RUNNER_TEMP=/tmp node --test .github/tests/integration/gateway.test.js
```

The integration fixture uses disposable networks, test certificates and request observers to verify Nginx syntax and forwarding. On the prepared host with both applications active, `python3 gateway/scripts/check_host.py` verifies live topology, peer addresses and unpublished backends. Acceptance of a production promotion belongs to the operator.
