# 🔐 Shared MCP authorization service

This independent Django service issues MCP grants at
`https://auth.judeandrewalaba.com` (no trailing slash). It reuses the pinned
FullStackTemplate settings/proxy helpers and Django OAuth Toolkit/OAuthlib for
OAuth protocol handling. It does not import application code, users or databases.
Normal Notoli and MacroMapper login remains application-owned.

## 🎯 Fixed application boundaries

| Resource | Public clients | Allowed scopes | Introspection client |
| --- | --- | --- | --- |
| `https://ynab.judeandrewalaba.com/mcp` | `ynab-chatgpt`, `ynab-codex` | `ynab:read`, `ynab:write` | None; offline pinned RSA key |
| `https://notoli.judeandrewalaba.com/mcp` | `notoli-chatgpt`, `notoli-codex` | `notoli:read`, `notoli:write`, `notoli:organize`, `notoli:notifications`, `notoli:delete`, `notoli:share` | `notoli-introspection` |
| `https://macromapper.judeandrewalaba.com/mcp` | `macromapper-chatgpt`, `macromapper-codex` | `macromapper:read`, `macromapper:write` | `macromapper-introspection` |

YNAB clients share one explicitly registered owner UUID. Application consumers
must separately map the immutable issuer UUID to an active local account and
enforce their existing permissions. A central account creates no application
membership. Cross-resource scopes, grants and introspection are rejected.

YNAB grants default to `ynab:read`. Write access requires an explicit request for
both `ynab:read ynab:write` and owner consent; refreshing a read-only grant cannot
add write permission. The gateway separately requires its reviewed deployment
write capability and preserves upstream exact-preview/human-confirmation checks.
Existing client registrations remain valid; no account or callback replacement
is needed when introducing the additional scope.

There is no signup, dynamic registration, client metadata URL fetching, general
identity platform, password grant, implicit grant or machine token issuance.
The two confidential introspection clients cannot obtain access tokens. Each can
inspect only its own application's audience, using POST form encoding and HTTP
Basic; bearer credentials and credentials in the form/query are rejected.

## 🔄 Protocol and revocation

Discovery is `/.well-known/oauth-authorization-server`. Endpoints are
`/o/authorize/`, `/o/token/`, `/o/revoke_token/`, `/o/introspect/`.
`/accounts/login/` and native DOT consent use secure Django sessions and CSRF.
Consent is required for every grant, including previously authorized clients.
Users revoke their own connections at `/o/authorized_tokens/`.

The consent page's browser policy permits form submission to the issuer and the
single callback origin already validated by DOT, including the actual Codex
loopback port. This lets Chromium follow the successful consent redirect. Login,
errors and other pages retain same-origin-only form submission. Never use a global
callback wildcard or derive this permission from unvalidated request parameters;
the exact callback/path, CSRF, PKCE, owner and resource checks remain mandatory.

Authorization codes expire after 120 seconds and require S256 PKCE. Register
exact HTTPS callbacks; Codex also supports RFC8252 literal loopback callbacks
(`127.0.0.1` or `[::1]`, variable ephemeral port). `localhost`, wildcards,
fragments and user information are rejected. The code exchange must repeat the
exact callback used for that authorization.

Access tokens are RS256 JWTs with `typ=at+jwt`, a key ID, fixed issuer, scalar
resource audience, UUID subject, client ID, scope, issuance/expiry and unique ID;
lifetime is 900 seconds. Refresh tokens remain opaque random library tokens,
rotate on use, expire after 30 days of inactivity measured from their paired
access-token expiry, and invalidate their family on reuse. This is DOT's sliding
idle-expiry policy, not an absolute 30-day lifetime for an actively rotated family. DOT's
RFC9700 token storage hashes access and refresh secrets. Introspection reads
current database state and verifies the JWT; it never caches successful results
or creates users. Disabled accounts, revoked grants and wrong audiences return
literal `active: false`.

YNAB's offline verification has a bounded remaining access-token lifetime after
central revocation (up to 900 seconds). Emergency containment disables ingress;
do not claim immediate offline revocation. Notoli/MacroMapper introspection can
enforce revocation on the next request.

## 📦 Runtime contract

The production image runs `auth_service.asgi:application` on port8000 and exposes
`python /app/manage.py`. Only `/data` is writable, with a uid65532-owned mode0700
directory holding `db.sqlite3` and its journals. Management and ASGI entrypoints
set umask0077. Do not bind only the SQLite main file or discard its journal.

Production reads uid65532-owned regular mode0400 files:

- `/run/secrets/django_secret_key`: independent Django secret, at least50 characters.
- `/run/secrets/signing_key.pem`: unencrypted RSA private key, at least2048 bits.

Set `MCP_AUTH_SIGNING_KEY_ID` to the reviewed public-key identifier and
`DJANGO_TRUSTED_PROXY_IPS=172.30.92.2`. Only the exact ingress proxy may supply
forwarded headers. Private health checks use server172.30.92.3 port8000:
`/health/live` is process liveness; `/health/ready` checks signing key and migrated
user table. Neither calls a financial API or provider. Disable access logs and
use ingress request/time/rate limits, particularly for password and token paths.
Bodies are bounded to16KiB/32 form fields; no external frontend/static assets
are required.

`requirements.txt` pins every Python distribution and exact Linux/amd64 wheel
hash. `dependency-wheels.json` records matching official PyPI artifacts, verified
before pinning. The Docker recipe installs only those binary wheels under
`/opt/auth-deps`, retains complete distribution metadata and checks dependency
closure. The immutable Python3.12.16 Alpine3.24 base requires no extra native
library copies; its build installer is removed from the runtime. Runtime pins
include Django5.2.18 LTS, Django OAuth Toolkit3.4.1, OAuthlib4.0.0, PyJWT2.15.1,
cryptography50.0.2 and Uvicorn0.54.0. A successful build is not artifact approval
or a substitute for the root image/dependency security gates.
Only the dependency-free canonical `__init__.py`, `config.py` and `proxy.py` are
needed in the runtime image. Retain this service's templates and migrations and
the upstream license notice; exclude tests and unused sample/framework runtime.

## 🧰 Closed operator setup and recovery

Production setup/promotion is separately authorized through the root runbook.
These management interfaces perform no provider calls and print no credentials:

1. `migrate --noinput` initializes the independent database while ingress is contained.
2. `bootstrap_mcp_owner --username NAME --password-file PRIVATE_FILE --subject-output PRIVATE_FILE`
   creates an account and writes its UUID to a new private file. Password input is
   a protected mode0400 service-owned file; no password command-line argument exists.
3. `register_issuer_client --resource ynab|notoli|macromapper --client chatgpt|codex --owner-subject UUID --redirect-uri EXACT_URI`
   creates one fixed client. Repeat `--redirect-uri` only for known exact callbacks.
   Existing IDs are refused. All YNAB registrations must use the same owner.
4. `register_mcp_introspector --resource notoli|macromapper --secret-file PRIVATE_FILE`
   installs the dedicated app credential. `--rotate` explicitly replaces an
   existing dedicated credential; coordinate its consumer file under containment.

For a contained DB restore, stop issuance, hold the release lock, restore the
SQLite directory coherently, run `revoke_all_mcp_grants`, and verify before
restarting. This command transactionally deletes codes, access tokens, refresh
tokens including rotation history, and Django sessions. Restoring old database
state without this invalidation would resurrect old authorizations.

Key rotation requires a reviewed matching private/public key pair and key ID,
contained release and explicit rollback. This version maintains one signing key;
old JWTs fail introspection after a key change and consumers need reconnection.
Coordinate YNAB's pinned public key with its release and revoke all grants when
recovering a key compromise. No zero-downtime key-rotation guarantee is made.

## 🧪 Source verification

Run `python services/mcp-auth/run_tests.py` against an isolated Docker Desktop or
local CI daemon. It builds an unpublished credential-free candidate, validates
inactive Compose, runs the full Linux source suite and actual production
entrypoint/bootstrap with synthetic file secrets, checks uid/modes and restart,
then removes only its labeled containers/volumes/image. CI can supply
`MCP_AUTH_TEST_ID=mcp-auth-test-<32 lowercase hex>` and invoke
`python services/mcp-auth/run_tests.py --cleanup ID` from its timeout trap.
No provider or production Docker context is permitted.

For a fast source-only check with installed dependencies, run
`python services/mcp-auth/run_source_tests.py`. This runner creates synthetic RSA
keys and an isolated SQLite directory, never loads production settings or
secrets, and removes its fixture afterwards. Tests
exercise real code/S256 exchange, exact callbacks, refresh rotation/reuse,
revocation, all three resource boundaries, owner restrictions, authenticated
introspection, CSRF/consent, grant management, key rotation, readiness failure and
cross-process persistence. Framework parity uses
`python services/mcp-auth/scripts/check_mcp_framework.py`; sync the full canonical
package and manifest from its immutable source pin, never edit the vendor copy.

After source/recipe changes, explicitly regenerate
`python services/mcp-auth/scripts/update_manifest.py --write`; omit `--write` to
verify it. `build.py --tag LOCAL_TAG --record NEW_PRIVATE_RECORD` builds from
only that manifest's verified files and records an unpublished/unapproved local
image ID. Publishing, full-image scanning and promotion use root release gates.
