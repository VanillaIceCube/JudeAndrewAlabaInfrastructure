# 🧹 Retire the external YNAB integration and shared MCP issuer

The owner's October 30 decision in #56, tracked by #96, supersedes the Oliver Ames YNAB rollout
and shared MCP authorization plan. Infrastructure owns nginx ingress; each
application owns its MCP implementation, OAuth, accounts and release. Existing
Notoli MCP stays enabled. MacroMapper MCP may remain unimplemented. A future
first-party YNAB application is a separate task, not part of this retirement.

The preparatory source change in #100 removed application build/runtime source,
the disposable experiment and their CI jobs. It temporarily retained six
deployment inputs/preflight helpers and the existing controllers. The final
cleanup in #99 removes the retired-service inputs/controllers and route
definitions while preserving ordinary ingress and app release support.
Promote the reviewed final cleanup source through the authorization below.

## 🚦 Ordered retirement

Each source merge, promotion and provider/host operation requires explicit owner
authorization and must stay within the designated operator's authorized scope.
Source changes require review and normal CI, merge to `main`, then promotion to
`env-prod`. Preserve history and unrelated fixes. The owner has asked Codex to
coordinate and execute this scoped retirement in the current session, recorded
in [#4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4#issuecomment-6530655656)
and #96. Record exact identities, operation plans and outcomes there and privately
in KnowledgeVault before/after execution. This runbook itself grants no merge,
promotion, provider, host or rollback authorization; unrelated operations and
future deployments require their own owner authorization.

1. Inventory accepted generations, pending barriers, exact app/container/network
   identities and the two DNS records. Log each provider request and purpose
   before execution and its result afterward. Do not expose secrets or financial
   data. Stop on unexpected ownership or an unfinished release transaction.
2. Promote this reviewed retirement decision with both existing route profiles
   set to `disabled`. Use the existing gateway transaction and verify the two
   origin 410 tombstones, unchanged Notoli/MacroMapper containers, exact Notoli
   proxy trust and ordinary app health. Do not remove active hostnames implicitly.
3. Use the accepted YNAB controller's `disable --confirm-stopped-attempt` path
   under its existing maintenance/app locks. The issuer has no disable command:
   execute a separately reviewed stop-only operator procedure under the exclusive
   maintenance lock and issuer lock. Validate its accepted record, ownership,
   image, database/journal mounts, both disabled routes and absence of consumers;
   write/fsync a private retirement pending record before `docker stop --time 30
   mcp-auth-server`. Verify that exact container is stopped and companions are
   unchanged, then durably record completion. An interruption retains the record
   and requires inspection, never automatic retry. Do not use issuer rollback or
   recovery as a substitute for retirement. Retain private financial journal and
   recovery evidence without replaying requests or restoring financial state.
4. Delete only the exact `ynab.judeandrewalaba.com` and
   `auth.judeandrewalaba.com` DNS records created by this rollout, after verifying
   their identities. Preserve all other DNS, TLS, WAF, cache and account settings.
   Keep tombstones while DNS caches can still refer to the retired services.
5. Remove the three stopped, ownership-verified YNAB/issuer containers and the
   four dedicated bridges only after verifying that they have no remaining
   consumers. Remove active credential/configuration copies and unused dedicated
   images/cache. Preserve a private offline retirement/recovery record and the
   owner's source notes; do not delete an application database or shared volume.
6. Through a second reviewed main-first change, remove the retired service,
   experiment, issuer, release and CI implementation. Restore the canonical
   app-owned MCP/release contracts and synchronize consumer pins. Use the
   accepted disabled gateway configuration to establish the ordinary three-network
   baseline before the simplified controller is used. Record this explicit
   retirement transition; never bypass a pending barrier or overwrite evidence.
   The simplified controller's read-only compatibility accepts only the exact
   matched disabled tombstone bytes on the ordinary three networks. It can
   forward-deploy the base configuration and restore those contained bytes on
   failure; it rejects enabled records and never recreates retired services.
7. Promote ready app cleanup through `main` and `env-prod`; do not create an
   `env-prod` branch in FullStackTemplate. Verify Notoli, MacroMapper and existing
   authenticated Notoli MCP. Remove obsolete client registrations/configuration,
   close superseded work with history intact and leave future YNAB work separate.

## 🔒 Recovery and completion

An interrupted mutation requires inspection of its persistent unit and durable
records before any explicit recovery. No broad Docker prune, host rebuild,
network recreation, force-push or blanket repository reset is part of this work.
Preserve nginx image/security updates and ordinary app functionality. Production
cleanup is complete only after the retired services are absent and existing apps
pass their checks; source deletion alone is not completion.
