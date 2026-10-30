# 🔐 Shared MCP authorization

Infrastructure owns one independently released authorization service at
`https://auth.judeandrewalaba.com`. This supersedes the managed-provider proposal
in #71. It uses maintained Django OAuth Toolkit/OAuthlib rather than a custom
OAuth protocol implementation. Its accounts, SQLite database and signing keys
are separate from Notoli and MacroMapper.

Clients authorize with this issuer, then call each application's MCP endpoint
directly. There is no shared MCP tool router. Applications retain their tools,
data permissions and independent releases. Their ordinary website login and
REST JWT authentication remain application-owned.

## 🎯 Resource and identity boundaries

| Application | Exact resource | Token validation | Scopes |
| --- | --- | --- | --- |
| YNAB | `https://ynab.judeandrewalaba.com/mcp` | Offline pinned RS256 public key, fixed owner and clients | `ynab:read` |
| Notoli | `https://notoli.judeandrewalaba.com/mcp` | Authenticated, uncached issuer introspection plus explicit local user link | Existing six `notoli:*` scopes |
| MacroMapper | `https://macromapper.judeandrewalaba.com/mcp` | Authenticated, uncached issuer introspection plus explicit local user link | `macromapper:read`, `macromapper:write` |

Each app has distinct ChatGPT/Codex client IDs. Notoli and MacroMapper also have
separate confidential introspection clients restricted to their own resource;
these cannot obtain access tokens. A central account grants no app membership.
Applications explicitly link the immutable issuer/UUID subject to an existing
user and recheck local active status and object permissions on every operation.
Never infer a link from an email address or silently create/merge users.

One issuer shares an administrative and availability boundary. Compromise of its
signing key or privileged operator affects all MCP resources. Separate audiences,
scopes and clients prevent accidental token reuse; they do not isolate a malicious
issuer administrator. Ordinary app login continues during issuer outages.
Introspection consumers fail closed; existing YNAB access tokens have bounded
offline validity, while new authorization/refresh requires the issuer.

## 🔄 Protocol and revocation

The [service contract](../services/mcp-auth/README.md) defines fixed endpoints,
closed operator registration, authorization code/S256, explicit consent, refresh
rotation/reuse handling and client callback validation. Dynamic registration and
public signup are disabled. Register actual client callbacks; do not invent a
callback from an application hostname or use a wildcard.

Access tokens are RS256 `at+jwt` tokens with exact issuer, resource, UUID subject,
client, scope, issuance/expiry and token ID. Their lifetime is at most 900 seconds.
Refresh tokens remain opaque and library-managed. Consumer introspection verifies
current grants, signature, user and resource without caching successful results.

YNAB's offline verification can accept an already-issued token for its remaining
lifetime after central revocation. Emergency disablement uses its 410 ingress
profile. Authorization-database restore must revoke restored grants/sessions and
keep YNAB contained for at least 905 seconds before re-exposure, covering the
maximum token lifetime and accepted clock skew. The release controller records a
durable quarantine that the ingress promotion must enforce; rollback must not
erase or shorten it. Do not describe database revocation as immediate offline JWT
revocation.

## 📦 Source, secrets and rollout

The canonical FullStackTemplate framework source is pinned to
`5a9294d550ec946a51b34bb2438a6c04ecc13461` (tracker #259, source PR #260).
Consumers synchronize its manifest and package instead of independently editing
vendored copies. The issuer runtime uses only its settings/proxy helpers; app
resource servers provide their own verifier to the shared external-issuer seam.
There is no runtime dependency on the template or another app's database.

The issuer's private Django secret and RSA signing key are file-only, uid65532,
mode0400. Its entire SQLite directory, including journals, is protected persistent
storage. YNAB retains its file-only financial token and offline public key.
Application introspection credentials use their existing private backend environment
bundle convention. Privileged Docker/host operators can read container environment;
this convention is not an adversarial boundary against those operators.

Prepare app source concurrently, then accept YNAB in both clients before later
Notoli/MacroMapper activation. Existing Notoli grants remain for deliberate rollback;
they are not interchangeable with central grants. Scope the client reconnection and
app user-link operations explicitly. FullStackTemplate remains a reusable optional
foundation, not another production app to deploy.

Issue #56 holds sanitized progress, exact operational authorization and owner
follow-ups. Private identities, recovery evidence and each Cloudflare/DigitalOcean
request's purpose/result belong in KnowledgeVault. The additional issuer's storage,
keys, DNS and capacity require the specific reviewed operational delta requested
in the owner's architecture decision. Source approval never replaces artifact,
capacity, recovery or real-client acceptance gates.
