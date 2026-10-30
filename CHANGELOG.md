# 📝 Changelog

## 2026-10-30

### Fixed

- Allow the validated MCP client's callback origin on its consent page so Chromium
  can complete authorization, preserving exact callback and OAuth checks.

### Changed

- Reconcile existing production promotion history into main and document
  main-first releases, prompt return of exceptional deployment fixes, and
  intentional release holds for unready source changes.
- Clarify final ChatGPT callback verification after discovery and Codex's
  metadata-derived resource setup, preserving strict issuer validation.

### Removed

- Retire the external YNAB runtime, gateway, egress proxy and shared MCP issuer,
  their rollout controllers, dependency scanners and isolated CI suites (#96).
  Restore app-owned MCP/OAuth routing and preserve exact disabled gateway
  recovery compatibility, existing app networks and historical release evidence.
- Remove central-issuer topology/mode assumptions from canonical release tests;
  retain the generic required-environment fixture and independent app releases.

## 2026-10-29

### Changed

- Give the staged YNAB egress policy its service-owned read-only permissions,
  preserving private release parents and exact matched-file recovery checks.
- Enable explicitly consented full YNAB MCP access with separate read/write scopes,
  preserved upstream previews and a persistent operation journal that code/image
  rollback never rewinds. End the current rollout after YNAB and existing-app checks.
- Honor Compose null image-default entrypoint/command inheritance in issuer
  runtime verification, preserving exact process checks and pending recovery.
- Pin the shared proxy to official Nginx 1.31.8 Alpine slim after complete native
  package assessment and TLS, gzip, streaming, DNS and recovery validation.
- Require strict issuer readiness for active central MCP consumers, preserve
  explicit disabled maintenance, and validate legacy gateway adoption separately.
- Match Notoli's explicit `legacy` MCP mode in shared release fixtures while
  preserving exact topology guards and rejecting unsupported modes.
- Supply synthetic app-specific required secrets only in disposable shared release
  fixtures; retain production missing/empty/malformed input rejection.
- Normalize parsed Compose memory bytes before exact YNAB runtime comparisons;
  test actual canonical staging with synthetic protected files in Linux CI.
- Separate YNAB stop-only containment from freshly scanned active-image rollback;
  require explicit stop-only recovery after an initial activation failure.
- Compare Alpine image coverage using native package names and complete installed
  versions while preserving Debian/Ubuntu epoch/revision and vulnerability gates.
- Replace the blocked YNAB gateway OS base with pinned Alpine stages and signed,
  hashed C++ packages; verify complete native APK scan coverage.

- Move the inactive YNAB gateway candidate to pinned Node/Python slim trixie
  stages and native tracked C++ libraries; retain fresh artifact security gates.

### Added

- Document the ordered YNAB/shared-issuer first activation, exact artifact/network
  prerequisites, both-client acceptance and contained recovery before app adoption.

- Add fixed inactive auth ingress, contained single-container issuer releases and
  journal-preserving SQLite recovery with grant invalidation and offline JWT
  quarantine; retain independent app releases and explicit recovery barriers.
- Route MacroMapper MCP/discovery exactly to its app backend, preserve its existing
  gateway peer172.20.0.3, and validate legacy/central app readiness without changing
  ordinary login, frontend or estimation routes.
- Add an inactive, independently packaged MCP authorization service with isolated
  app resources, maintained-library PKCE/consent/refresh/revocation, protected
  state/keys and pinned canonical framework policy; preserve ordinary app login.
- Extend existing dependency and full-image audit gates for its exact hashed
  Python lock and native/runtime inventory; run credential-free issuer container
  acceptance in Required CI without publishing or activating the service.
- Extend the existing gateway transaction with explicit YNAB profile packaging,
  protected tombstone transitions, route identity and independent health checks.
- Add an owner-operated YNAB-only stage/promotion/rollback controller using shared
  host primitives, fresh paired artifact scans, matched private files and durable
  recovery barriers; test actual Docker upgrades and SIGKILL without live services.
- Add a pinned Canonical Squid recipe with hash/version-pinned Ubuntu OpenSSL
  fixes, native package inventory and existing isolated CONNECT/stdio acceptance;
  require independent immutable egress and gateway image references.
- Add a pinned full-image YNAB audit prerequisite that rejects missing package
  coverage, stale evidence, secrets and high/critical vulnerabilities; retain
  explicit artifact/license/provenance and production activation gates.
- Add inactive YNAB ingress/disable profiles and isolated route/CONNECT-egress
  contracts with disposable DNS/streaming/rollback/TLS API tests; apply no provider changes.
- Add an inactive owner-authenticated FastMCP gateway with principal-bound isolated
  stdio children, read-only tool policy, bounded requests, safe readiness/errors
  and synthetic image acceptance in Required CI; provision no OAuth provider or ingress.
- Add the pinned FastMCP fallback dependency lock and fail-closed OSV/PyPI metadata
  checks in existing Required CI; retain unknown-malware, provenance and activation gates.
- Add a pinned, non-root, read-only YNAB stdio runtime candidate with package/source
  parity checks, protected token-file policy, no-network Compose profile and bounded
  disposable CI tests; retain production dependency/security and activation gates.

## 2026-10-28

### Added

- Document the conditional YNAB MCP gateway choice, dependency/security blockers,
  identity/route contracts and ordered #57–#62 handoff; add a pinned disposable
  upstream protocol/preview experiment in existing validation CI without production
  configuration or credentials.

### Fixed

- Record the previously undocumented [PR #25](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/pull/25) fix (merged 2026-10-18): emit bounded CI reports to stdout when `GITHUB_OUTPUT` is absent, avoiding a local-execution `KeyError` while preserving GitHub Actions output formatting.

## 2026-10-27

### Fixed

- Align strict security-alert token-action assertions with the reviewed v3.3.0 immutable pin while preserving credential and permission checks.

### Changed

- Update CodeQL init/analyze together to v4.39.1 and Gitleaks to v3.0.0.
- Pin Docker login v4.7.0 in the shared release template so application dependency updates retain deployment parity.

## 2026-10-20

### Fixed

- Fail closed on incomplete dependency reviews and retain sanitized structured evidence with a bounded RoboCop report.
- Preserve alert history and Project metadata before auto-close; verify concurrent closure without suppressing unrelated API errors and use the current Work type field.


## 2026-10-20

### Added

- Define the optional multi-app MCP ingress/readiness/onboarding contract and an inactive generic vhost example, with isolated enabled/ordinary app routing checks.

### Changed

- Share Notoli's exact MCP transport directives through an opt-in Nginx include and apply no-store policy to discovery; keep MacroMapper's live MCP profile disabled.


## 2026-10-20

### Changed

- Use repository Actions settings for gateway SSH configuration, with owner/branch/source/workflow checks before credential loading and contents-read-only tokens; remove GitHub Environment policy and Deployment API dependencies.
- Record promoted versus running gateway identities in sanitized Actions summaries and the durable host journal; report runner failure/cancellation without asserting a host outcome, and document verified settings migration, cleanup and repository-secret exposure.
- Align agent/reviewer policy with the owner-selected repository-only gateway settings model, including its workflow-writer trust boundary; preserve all required reviewer gates.

## 2026-10-19

### Changed

- Require Obi-Wan, Lint Eastwood and RoboCop reviews for same-repository Dependabot PRs, matching the application/template reviewer eligibility; retain fork exclusions and manual owner merging.
- Require six reviewer secrets in both Actions and Dependabot, and derive Required CI review applicability from the PR source repository for both human and bot authors.

## 2026-10-19

### Changed

- Separate Obi-Wan, Lint Eastwood, and RoboCop OpenAI secrets, including RoboCop alert aggregation; pass only each reviewer's own credentials, stage `OPENAI_REVIEWERS_PROJECT_ID` independently, and document the deferred per-repository key migration.

## 2026-10-19

### Changed
- Standardize gateway SSH configuration on DEPLOY_* names, one private-key secret and four connection variables; derive known-host pinning only after exact fingerprint verification and retain the renamed dedicated key's identity.
- Deploy reviewed gateway source automatically when the owner promotes it to env-prod, without a second reviewer or per-release approval variable; verify original/retrying owner identity, the environment branch restriction and exact current source.
- Align repository reviewer policy with owner-authorized gateway promotion while preserving independent scans, required source reviews and explicit recovery authorization.

### Fixed
- Accept regular gateway promotion merge commits only when their complete Git tree matches reviewed main, while preserving exact-source and environment approval checks.

## 2026-10-18

### Added
- Add disabled-by-default gateway deployment from separately approved `env-prod` revisions, protected environment policy checks and pinned SSH host-key negotiation.
- Add private versioned gateway staging, exclusive maintenance locking, bounded public/origin readiness, durable interruption barriers and gateway-only rollback.
- Add promoted/running-source tracking, no-restart handling for unchanged gateway configuration, and disposable release/recovery regression coverage.
- Document operator adoption, production approval prerequisites, retry, rollback and recovery retention.

### Fixed
- Revalidate current app identities during interrupted gateway recovery after reboot, while preserving route-network IDs and exact proxy trust.
- Preserve verified deployment success when retiring older records fails or a later runner finalizer executes.
- Keep explicit gateway rollback independent of unused candidate archive creation or transfer.

## 2026-10-18

### Added
- Exercise all shared release suites for the two existing app policies and an isolated FullStackTemplate onboarding fixture.

### Fixed
- Derive release preflight test networks and containers from app policy instead of assuming every non-Notoli consumer is MacroMapper; retain explicit existing-app trust and secret assertions.

### Changed

- Updated Nora and Marty to v3: one open PR per agent, with repeat runs maintaining the existing PR and integrating current main.

## 2026-10-11

### Added
- Add infrastructure Obi-Wan, Lint Eastwood and RoboCop reviews with tested inline publishing, prior-review history and visible failure gates.
- Add Python, JavaScript and Actions CodeQL analysis, Dependency Review, Gitleaks, actionlint/ShellCheck and explicit package scanner applicability checks.
- Add weekly Actions/Compose Dependabot updates and daily/manual security-alert issue reconciliation for Infrastructure Project #13.
- Document credentials, least-privilege tokens, scanner scope and activation acceptance.

### Changed
- Require independent checks and applicable reviewers without auto-merge, source mutation or production workflows.
- Include all alert severities and adapt security metadata to Project #13's Work type field.


## 2026-10-11

### Fixed
- Give MacroMapper backend responses a two-minute upstream read timeout so slower meal estimation can return within the companion app's 110-second AI budget.
- Verify a real delayed upstream response beyond the former 60-second proxy limit in the disposable ingress suite.

## 2026-10-11

### Added
- Add host-owned ingress Compose, Nginx routes, topology validation and the reviewed cutover/reversal guide.
- Add SQLite snapshot/restore validation including live container-local WAL, plus disposable ingress/recovery tests.
- Add versioned common app release tools, workflow template, shared deployment tests and pinned-source parity enforcement for Notoli and MacroMapper.
- Add repository contribution/agent guidance, a pull-request template, editor conventions and the owner's Modified MIT non-commercial license.

### Fixed
- Identify public readiness requests as `JudeAppRelease/1.0` so Cloudflare accepts the deployment client while preserving all response checks.

### Changed
- Archive preparation chronology in coordination #4, correct approval/implementation status and clarify cutover-only snapshot ownership.
- Document the approved architecture, app-specific deployment contract and intentional parity differences.
- Align repository documentation with the emoji headings and navigation used by the application repositories.

No production changes are implied by this source release; merges and operations require separate owner approval.
