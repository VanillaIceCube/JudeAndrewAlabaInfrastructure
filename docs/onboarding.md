# Adding an application

1. Obtain owner architecture/admission approval after measuring peak CPU/RAM,
   disk plus retained releases/backups and concurrent-release headroom. The
   present VM is not certified for a third app by these tests.
2. Give the app its own project, data/env directories and route network. Record
   exact IPAM, permitted membership and namespaced upstreams. Keep database and
   unrelated backend networks off ingress; review any exact-IP proxy trust.
3. Add a vhost here with runtime Docker DNS, canonical Host, overwritten
   forwarding metadata and direct backend paths. Preserve URI/query encoding;
   review streaming, no-store and query-safe logging. Test while app is absent.
4. Verify domain/DNS, origin SANs and Cloudflare cache/WAF/TLS policies. The
   host operator owns certificates; no app bundle contains keys or vhosts.
5. Give the app an app-only release pipeline: digest identity, private unique
   staging, protected host/app locks, consistent database backup, matching
   recovery config/env/images, bounded readiness and explicit data rollback.
6. Record backup destination/retention/restore owner, bounded logs, availability
   and resource alerts, response ownership and capacity upgrade triggers.
7. Prepare and validate code in separate PRs, obtain each merge approval, then
   a separate command-level production approval. Prove independent redeploy and
   recovery without changing existing apps/ingress before declaring completion.

This repository provisions no networks automatically. Existing app route
networks are adopted externally in place. A new app's network creation is an
explicit operator action in its approved onboarding plan.
