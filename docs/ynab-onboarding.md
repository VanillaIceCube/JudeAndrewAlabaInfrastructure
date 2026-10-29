# ✅ YNAB first-activation checklist

This is the #62 operator plan, not evidence of live acceptance or authorization
to execute it. The goal is read-only YNAB in **both ChatGPT and Codex**. Reuse the
existing host, gateway, release tooling and monitoring; no new infrastructure
platform or regular-app authentication migration belongs in this activation.

## 📋 Before authorizing production

- Merge the reviewed dependency PRs in order, with required CI and all reviewers
  passing. Record exact source commits, upstream pin, gateway/egress registry
  digests, native package inventories, fresh scans and license/provenance review.
  A local image ID is not a published registry manifest digest.
- Designate the operator in #4 and record exact authorization in #62. Keep
  `env-prod` held: its current promotion would include unrelated ingress work.
  Isolate that promotion or explicitly review and authorize the combined change.
- Approve the [managed OAuth settings](mcp-oauth.md); create the dedicated issuer
  and two exact client registrations. Store private identity/callback/key details
  in KnowledgeVault. Confirm account/plan terms before any paid commitment.
- Owner creates a YNAB personal access token through the
  [official API developer settings](https://api.ynab.com/)
  and privately provisions it with the identity and issuer public key using the
  [existing protected-file contract](../services/ynab-gateway/README.md).
  Never put credentials in GitHub, CI, command arguments or chat. The personal
  token is not read-only at YNAB; the gateway's tool policy enforces read-only use.
- Review real host capacity, disk/export headroom and scanner resource limits.
  The gateway/proxy limits are additional load; local success or droplet specs
  do not establish spare production capacity. Stop if there is insufficient room.
- Record existing app/container/network identities, exact Notoli proxy trust,
  certificate hashes and recovery state privately. Check all proposed subnets
  against real host/VPC routes before authorizing new objects.

## 🚦 Authorized sequence

Log **each** Cloudflare/DigitalOcean request and purpose privately before execution,
then its result and any mutation. Publish a sanitized change list and remaining
owner actions on #56. Do not use provider calls to test whether credentials work.

1. Establish the reviewed `disabled` tombstone through the
   [existing gateway path](gateway-profiles.md). Verify origin TLS/410 before DNS.
2. Provision only the approved [YNAB network objects and DNS/TLS](ynab-ingress.md).
   Preserve all existing network IDs, application trust and default hosts.
3. Publish/load the independently approved immutable images. Use the
   [YNAB release controller](ynab-releases.md) under the documented persistent
   unit/locks. Re-scan both roles, stage matched files and verify private readiness.
4. After issuer/client/artifact/capacity acceptance, authorize the explicit
   enabled gateway profile. Check public and origin TLS, uncached anonymous 401
   and exact protected-resource/issuer metadata. No financial call is a health probe.
5. Connect each client separately using its own registration. In each, initialize,
   list tools, and make one owner-approved read of a chosen budget/categories or
   aggregate counts. Keep values and raw responses private; record only pass/fail.

## 🧪 Acceptance and containment

For **each client**, record successful login/read, reconnect, token renewal or
deliberate relogin, and revocation behavior. Reject anonymous, wrong-owner,
wrong-client and wrong-resource requests. Verify hidden write/admin tools and
exact callback matching and S256 PKCE enforcement at the issuer. Also verify
`YNAB_ALLOW_WRITES=0`; do not attempt a real financial write as a negative test.
Confirm Notoli/MacroMapper health and all unrelated identities remain unchanged.
Use existing #24 monitoring for nonfinancial health; no new monitoring daemon.

On failure, preserve private evidence and pending barriers. Disable public access
with the 410 gateway profile, then use the app's explicit matched rollback/recovery;
these are independent operations. Do not recreate networks or retry ambiguous
mutations. Stop/revoke the YNAB token and both OAuth grants for credential incidents;
reissue matched files through the same app lock. Follow the existing recovery
guides rather than deleting records or live volumes.

Close #62 only after real acceptance in both clients and sanitized owner sign-off.
Keep Notoli #973 blocked until then. Source/synthetic tests do not satisfy these
unchecked production criteria.
