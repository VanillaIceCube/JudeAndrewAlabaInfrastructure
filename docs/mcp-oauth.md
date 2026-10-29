# 🔐 Managed MCP OAuth

Infrastructure owns the provider configuration and deployment contract under
[#71](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/71).
Applications retain tool permissions and business authorization. Ordinary website
and REST login are unchanged. YNAB comes first; Notoli migration #973 waits for
actual #62 acceptance, and MacroMapper's existing #284 remains future work.

## 🎯 YNAB provider settings

Use a dedicated **Auth0 tenant for YNAB MCP**, managed from the same Infrastructure
process that future apps can reuse. Future apps keep separate issuers/tenants,
resources, client registrations and credentials to preserve independent recovery.
This adds no self-hosted authorization server or identity database. No tenant,
billing plan, connection or credential has been created by this source change.

Auth0 supports native MCP resource indicators; enable its **Resource Parameter
Compatibility Profile** rather than translating `resource` through a custom proxy.
See [Auth0's MCP support](https://auth0.com/blog/auth0-auth-for-mcp-servers-generally-available/)
and [resource-parameter configuration](https://support.auth0.com/center/s/article/mcp-audience-error-with-auth0).
Confirm feature availability in the owner's selected plan before creation; this
plan assumes neither a paid commitment nor a custom domain.

| Setting | Required value |
| --- | --- |
| Issuer | Exact HTTPS tenant issuer, including its trailing slash; keep in private identity file |
| API identifier/resource | `https://ynab.judeandrewalaba.com/mcp` |
| Signing/token profile | RS256; RFC 9068 (`rfc9068_profile`), `typ: at+jwt`, `client_id` claim |
| Access-token lifetime | At most 900 seconds for this API, including browser flows |
| API permission | `ynab:read`; no write or admin permission |
| Clients | Separate pre-registered ChatGPT and Codex public clients; native type, token authentication `none`, authorization code with S256 PKCE |
| Callbacks | Exact values shown by each installed client; no wildcard or copied example callback |
| Grants | Authorization code; rotated refresh tokens only if explicitly configured and tested for both clients |
| Login | Owner's selected connection; disable open signup; gateway also fixes one exact owner subject |

[Auth0's RFC 9068 profile](https://auth0.com/docs/secure/tokens/access-tokens/access-token-profiles)
uses `client_id` and can issue an audience array containing the API and its own
userinfo endpoint. The gateway accepts only the YNAB resource, optionally that
exact issuer-local endpoint; another app audience, owner or client is rejected.
The pinned public-key, lifetime, scope and session-owner checks remain mandatory.
[Native public clients use token authentication `none`](https://support.auth0.com/center/s/article/Login-failed-PKCE-NOT-ALLOWED-error-after-logging-in-on-a-Native-application).
Do not add client secrets, DCR, token exchange or custom login Actions for this
initial predefined-client setup.

## 🔌 Connect both clients

Follow [OpenAI's MCP OAuth contract](https://developers.openai.com/plugins/build/auth)
for discovery and the ChatGPT linking UI. Register the actual callback it shows;
the stable callback depends on issuer-response support. Configure the ChatGPT
client ID and select only read access. Never paste access tokens into chat.

For Codex, follow the [current MCP setup guide](https://learn.chatgpt.com/docs/extend/mcp):
first run `codex --version` and `codex mcp add --help`. The selected executable
must advertise `--oauth-client-id`; older globally installed CLIs do not support
this flow. If PATH selects an old CLI, use the compatible executable bundled
with the installed desktop app. If none is available, keep Codex acceptance
blocked until a supported client is installed; do not enable DCR or weaken the
fixed-client policy to work around it. Use that same executable for both commands:

```sh
codex mcp add ynab --url https://ynab.judeandrewalaba.com/mcp --oauth-client-id YOUR_CODEX_CLIENT_ID
codex mcp login ynab --scopes ynab:read
```

Register the complete callback printed by the installed client, preserving its
path and the provider's supported loopback-port behavior. Keep client config
private. Validate refresh/relogin independently; initial authorization does not
prove renewal works. No refresh token is stored by the gateway.

Privately record the issuer, fixed owner subject, two client IDs, exact callbacks,
consent/revocation settings and signing-key fingerprint in KnowledgeVault. Export
only the provider's RSA public key into the existing protected file contract;
never deploy a signing private key. Offline pinning deliberately requires an
operator-controlled key update and app recreation when the provider rotates keys.
Access tokens can remain valid for their remaining 15-minute lifetime after a
grant is revoked; disable the route for immediate containment.

The [onboarding checklist](ynab-onboarding.md) supplies the separate activation
and both-client acceptance gates. Provider setup and production operations need
their own exact owner authorization; a source merge supplies neither.
