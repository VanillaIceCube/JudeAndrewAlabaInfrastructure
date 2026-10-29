# 🛠️ Working in this repository

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

Follow [the gateway decision](docs/ynab-mcp.md) and #56/#57–#62 dependency order.
The disposable `experiments/ynab-mcp` harness is not deployable application code.
Run it with Node 24 for harness/pin changes; existing validation CI enforces the
same credential-free experiment with a four-minute limit.
Keep upstream source/lock pins, one stdio child per logical session, independent
owner identity boundaries and `YNAB_ALLOW_WRITES=0`. Do not ship fixture tools,
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
offline pinned issuer public keys, fixed owner/client/resource, hidden write/admin
tools and no retries after child failure. Production/provider/client acceptance
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

Use the [YNAB-only release contract](docs/ynab-releases.md) for its stateless app
controller. Keep paired fresh scans under shared maintenance/exclusive app locks,
matched private files/images, durable pending barriers and explicit recovery.
Never retry ambiguous Docker mutations, accept saved approval JSON or mutate
ingress/networks/other apps. Run both `test_ynab_release*.py` state/Docker suites;
source tests substitute only synthetic providers, never a production bypass.

The [YNAB stdio runtime](services/ynab-mcp/README.md) uses its canonical
`upstream.json` pin and unchanged upstream code. Run its disposable container
suite for runtime/pin changes. Keep the initial profile network-disabled,
uid 65532, read-only, token-file-only and financially read-only. No source PR
approves a production image, provisions a credential or supplies live acceptance.
