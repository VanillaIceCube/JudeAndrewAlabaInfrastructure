# JudeAndrewAlabaInfrastructure
Source of truth for shared Docker ingress, Nginx routing, security, and operations for judeandrewalaba.com applications.

Coordination and owner decisions live in [issue #4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4).
Agent 5 owns source changes across this repository, Notoli, and MacroMapper;
Agent 3 independently inspects the VM and is the sole operator after separate
production authorization.

The [v2 architecture contract](docs/architecture-v2.md) is
[owner-approved](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4#issuecomment-6111586759).
It reconciles the earlier audits and defines the implementation and validation
gates. It does not authorize a merge or deployment. The existing live ingress
remains app-owned until an approved cutover is executed and verified.

Implementation: [Compose](compose.yml), [Nginx](nginx/nginx.conf),
[cutover/reversal](docs/cutover.md), and [new-app checklist](docs/onboarding.md).
Run `docker compose -f compose.yml config --quiet` and
`python -m unittest discover -s tests -v` on a disposable local/CI Docker daemon.
The integration test uses generated certificates, unique test networks and
loopback ephemeral ports; it never invokes the production runbook.
