# 🛠️ Working in this repository

The owner's October 30 decision retires the external YNAB integration and shared
MCP issuer. Follow [the retirement sequence](docs/mcp-retirement.md) while cleanup
is underway; it supersedes the activation plans below. Preserve existing Notoli
MCP and route future MCP services to each application's own implementation/OAuth.

This repository owns shared ingress and the versioned application release
standard. Read [README.md](README.md), the [architecture](docs/architecture-v2.md)
and the [release standard](docs/app-release-standard.md) before related changes.

- Keep app releases independent. Preserve existing network objects, exact Notoli
  proxy trust, immutable images, SQLite journal recovery and explicit rollback.
- Update the relevant guide and [CHANGELOG.md](CHANGELOG.md) when behavior,
  configuration or operator steps change. Use concise emoji-prefixed headings
  consistent with the neighboring application repositories.
- Change common release code under `app-release/v1`, regenerate its manifest,
  then synchronize both app PRs to the same commit. Do not edit vendored copies
  independently. App configuration and Compose remain app-specific.
- For the owner-approved central MCP adoption in #56/#71, follow the explicit
  legacy/central policy table in `docs/app-release-standard.md`. Both exact
  topologies are intentional supported source configurations; preserve the
  independent legacy-fixture anchor and exact existing peers in either mode.
- Validate Compose and run `python -m unittest discover -s tests -v` against a
  disposable local/CI Docker daemon. Also run
  `python scripts/update_release_manifest.py --check`; shared behavior changes
  require both applications' deployment suites and parity checks.
- Follow [CONTRIBUTING.md](CONTRIBUTING.md) for review and validation. Never run
  the production cutover guide as a test or expose private recovery/env/key data.

Owner decisions are recorded on [issue #4](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4).
Architecture approval does not authorize merging, release-branch promotion or
production operations. Use issue #4 for the designated operator and exact
production authorization; do not infer either from source approval. Repository automation in issues #5–#9 is owner-prioritized; follow the
[workflow guide](.github/README-WORKFLOWS.md). Implementation approval still
does not authorize merging or production operations.

## 🚀 Gateway promotion authorization

Ordinary changes must merge through reviewed `main`, with explicit owner approval
for the merge, before separately authorized `env-prod` promotion.
An explicitly owner-authorized quick deployment experiment must be reconciled
back into `main` through review promptly. Preserve both histories and newer main
work; never force-push for parity. Intentional unreleased main changes may remain
ahead of production until their deployment prerequisites are met. Follow the
[main-first release policy](https://github.com/VanillaIceCube/FullStackTemplate/blob/main/docs/SHARED-ROLLOUT-POLICY.md#main-first-releases).

The owner's [October 19 decision](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/4#issuecomment-6273538610)
authorizes automatic gateway deployment when the owner promotes reviewed main
source to `env-prod`. The owner-triggered promotion is production authorization;
no second reviewer or per-release approval variable is required. Manual retries
must also be owner-triggered. Initial host setup and explicit gateway recovery
retain their separately authorized operator scope. Application release rules
and the one-time cutover are unchanged.

The owner's [gateway settings decision in #41](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/41)
uses repository Actions secrets and variables only. No GitHub Environment or
Deployment API record is required. Preserve owner/branch/source/workflow checks,
credential-free authorization before key loading, restricted triggers, fingerprint
pinning, least privilege and host recovery evidence. Repository secrets have no
branch-scoped access boundary; arbitrary workflow writers remain privileged.
Document that exposure rather than claiming helper checks constrain other workflows.

## Jules recurring agents

Nora and Marty use the [v3 operating rules](.jules/README.md): at most one open
PR per agent per repository. Repeat runs maintain the existing PR, integrate
current main, and verify its latest head instead of opening another PR.

## 🔑 OpenAI reviewer isolation

Use `OBI_WAN_OPENAI_API_KEY`, `LINT_EASTWOOD_OPENAI_API_KEY`, and
`ROBOCOP_OPENAI_API_KEY` for their respective reviewers; RoboCop also owns
all security-alert model calls. `OPENAI_REVIEWERS_PROJECT_ID` identifies this repository's
reviewer project. Keep credentials separate across repositories and application
environments, preserve visible missing-key failures, and follow the deferred
cutover steps in `.github/README-WORKFLOWS.md`.

## 🤖 Dependabot AI reviews

Trusted same-repository Dependabot PRs require the same three reviewers as human
PRs. Keep forks excluded and all applicable reviewer failures blocking Required
CI. Store the three reviewer OpenAI keys and three GitHub App private keys in
both Actions and Dependabot; production/Project-token secrets stay outside
Dependabot. Preserve immutable action references, non-mutating reviews and
manual owner merge. A human PR smoke test does not prove Dependabot access.


## 🔌 Optional MCP applications

Follow the [optional MCP contract](docs/optional-mcp.md) for app-owned ASGI/OAuth, shared ingress, readiness and rollback. Notoli remains enabled; MacroMapper is not advertised until its application registry is ready. Preserve independent releases and exact app proxy trust.

## 🧾 YNAB MCP investigation

For actual client acceptance, follow `docs/ynab-operations.md`: verify callbacks
after discovery and keep exactly one OAuth resource parameter. Correct client
configuration rather than weakening issuer resource or redirect validation.

Follow [the gateway decision](docs/ynab-mcp.md) and #56/#57–#62 dependency order.
The disposable `experiments/ynab-mcp` harness is not deployable application code.
Run it with Node 24 for harness/pin changes; existing validation CI enforces the
same credential-free experiment with a four-minute limit.
Keep upstream source/lock pins, one stdio child per logical session and independent
owner identity boundaries. The owner's #56 scope change enables full YNAB features:
base images stay `YNAB_ALLOW_WRITES=0`; the reviewed deployment opts in to writes,
and each child additionally requires an explicit `ynab:write` grant. Do not ship fixture tools,
fork/vendor Oliver's application, or treat native gateway keys as public OAuth.
The evaluated gateway pin has unresolved high/critical advisories: public ingress,
credentials and activation remain blocked pending #58/#59 review and separately
authorized operations. Keep sanitized progress on #56 and private details in
KnowledgeVault. Log each Cloudflare/DigitalOcean request and purpose privately
before execution, then record its result and any mutation; do not log secrets.

#59 reopens the conditional gateway choice with pinned FastMCP 4.1.4; see
`services/ynab-gateway/README.md`. Only its exact hashed Python lock has scanner
support. Run `python scripts/check_gateway_dependencies.py` for lock changes;
never bypass unsupported-manifest checks or treat known-advisory checks as proof
against unknown malware. Run `python services/ynab-gateway/run_tests.py` on a
disposable daemon for gateway changes; regenerate its source manifest explicitly.
Keep one distinct transport per remote session (client clones share transports),
offline pinned issuer public keys, fixed owner/client/resource, exact scope checks
on concrete and generic tool dispatch, upstream preview/confirmation and no retries
after child failure. Production/provider/client acceptance
and network activation remain separately gated.

#60's [inactive routing/egress contract](docs/ynab-ingress.md) preserves all existing
network objects and Notoli trust. Keep the base ingress/profile inactive; use
exact MCP/metadata routes and the explicit 410 disable profile. Node's fixed
CONNECT proxy has no direct-bypass or caller-controlled authority. Never copy
the fixture private-IP ACL exception or CA into production. Run both ingress
suites and the gateway runner for route/egress changes; #61/#62 must approve
artifact/security/release/capacity and provider operations before activation.

#61's [artifact gate](docs/ynab-artifact-security.md) requires complete OS/runtime
inventory, a hash-pinned scanner and fresh evidence for both images. Never waive
the pinned Squid candidate's known HIGH findings or approve a zero-inventory scan.
Run `python -m unittest discover -s tests -p test_ynab_image_audit.py -v` for gate
changes. Scans neither approve licenses/provenance nor authorize deployment.
The [egress recipe](services/ynab-egress/README.md) pins official Ubuntu security
packages without a mutable resolver. Regenerate its recipe manifest and run the
gateway runner plus both full-image artifact scans for changes. Keep unpublished
local candidates distinct from approved registry digests.

The [gateway profile contract](docs/gateway-profiles.md) uses the existing bundle/
owner-promotion path. Preserve a disabled tombstone baseline before exposure,
exact Notoli trust and accepted optional-route identity; never implicitly remove
the hostname by reverting to `base`. No profile variable is a deployment approval.

Use the [YNAB-only release contract](docs/ynab-releases.md) for its app
controller. Keep paired fresh scans under shared maintenance/exclusive app locks,
matched private files/images, durable pending barriers and explicit recovery.
Never retry ambiguous Docker mutations, accept saved approval JSON or mutate
ingress/networks/other apps. Run both `test_ynab_release*.py` state/Docker suites;
source tests substitute only synthetic providers, never a production bypass.
Preserve the protected persistent upstream financial journal and its directory
identity across release/recovery. Code/image rollback must never rewind journal
bytes or imply that an external financial change was undone. No fork or replacement
journal engine is needed; use Oliver's existing implementation unchanged.

The [YNAB stdio runtime](services/ynab-mcp/README.md) uses its canonical
`upstream.json` pin and unchanged upstream code. Run its disposable container
suite for runtime/pin changes. Keep the initial profile network-disabled,
uid 65532, read-only root and token-file-only. Write-enabled children require the
protected persistent data directory and explicit OAuth permission. No source PR
approves a production image, provisions a credential or supplies live acceptance.

The gateway image uses pinned Python/Node Alpine stages and two hash-pinned,
signature-verified native APKs. Preserve complete APK inventory coverage in the
artifact gate, the unchanged hashed Python/Node graphs and stdio-only advisory
applicability; never copy untracked C++ libraries or waive image findings.

## 🔐 Shared MCP authorization

Follow [the MCP-only issuer contract](docs/mcp-oauth.md) and #71. The independently
released Django OAuth Toolkit service owns separate accounts, database and keys;
app tools, local user mapping and regular website/REST login remain app-owned.
Keep exact per-app resources/scopes/clients and audience-bound introspection.
Synchronize canonical FullStackTemplate source/manifest pins across consumers;
never edit vendored framework files independently. Run
`python services/mcp-auth/run_tests.py` against a disposable local/CI daemon and
audit its exact hashed dependency lock through the existing dependency gate.
Require native OS and complete Python inventory for authorization image scans;
supporting that role must not weaken the paired YNAB image gate.
Consent-page form redirects must allow only the DOT-validated callback origin,
including its actual loopback port; retain same-origin-only policy elsewhere.
Verify browser redirect behavior as well as server-side OAuth tests.

Use the [issuer release/recovery contract](docs/mcp-auth-releases.md) for its
single-container controller. Keep both auth/YNAB routes contained during database
operations, preserve full journal namespaces and durable rename recovery, and
invalidate restored grants/sessions before acceptance. The durable905second
quarantine must survive rollback; ingress cannot re-expose offline YNAB JWTs early.
Run all `test_mcp_auth*.py` suites on Linux/disposable Docker and preserve the
existing apps and their exact peer addresses throughout.
Interpret Compose null process fields as image defaults while checking the
effective entrypoint/command exactly; explicit empty overrides are not inheritance.

## 🚀 Coordinated MCP activation

Follow [first activation and client acceptance](docs/ynab-operations.md) for #62.
Use the existing issuer, YNAB and gateway controllers sequentially; keep exact
image/source identities, paired fresh scans, disabled tombstones and private
provider-request evidence. The current owner-authorized window ends after full
YNAB acceptance in ChatGPT and Codex plus health checks of Notoli, MacroMapper and
existing Notoli MCP; defer their migrations. Preserve ordinary app login and
upstream financial preview/exact-confirmation safeguards. Never replace actual callback registration or owner consent with
synthetic acceptance; retain every durable recovery/quarantine barrier.
