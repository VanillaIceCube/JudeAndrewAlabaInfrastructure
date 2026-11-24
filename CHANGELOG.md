# Changelog

All notable changes to this project are documented in this file.

## 2026-11-23

### Fixed

- Require an explicit gateway network allowlist during app preflight; reject unreviewed attachments while retaining independent recovery when approved companion routes are absent.
- Explain why failure-reporting stream errors preserve the original release outcome.

### Changed

- Cancel older CI runs when a new run starts for the same pull request.
- Install the pinned Actionlint release directly in the CI workflow.
- Inline CI validation and reporting in the workflows that use them.
- Remove the generated CI workflow inventory and its architecture drift check.
- Review GitHub Actions write permissions in workflow PRs and remove the separate approval file.

## 2026-11-22

### Changed

- Automatically select the checksummed saved controller and app policy for rollback under the existing locks; preserve the matching controller through subsequent recovery/deploy cycles and reject invalid saved controllers before migration.
- Keep app release preflight focused on app-owned route networks while the Infrastructure host checker retains full network membership, subnet, trusted-IP and backend-port validation.
- Show MCP, discovery and private-cache rules directly in each gateway vhost; preserve the fully expanded Nginx configuration.
- Add readable release and recovery progress, failing-step context, command exit codes and private-record pointers to the shared app release engine; preserve transaction order and private subprocess output.
- Put routine gateway promotion and recovery first in the existing guide; retain topology, initial adoption, migration history, commands and section links in the same README.
- Document application local deployment file names and their distinction from production release files and historical recovery evidence.

### Removed

- Stop copying retired app-root stack artifacts into new recovery sets and remove the missing recovered-policy fallback; preserve existing archives, runtime/SQLite recovery and gateway retirement guards confirmed by the read-only host inventory.
- Remove translation of the three retired custom Resend backend names from new release bundles; require an explicit maintained Anymail or SMTP selection while preserving retained recovery bundles.
- Remove nested MCP/cache snippets, unused legacy/vacant host-check modes, the repeated frontend build-argument selector and the completed consumer parity-checker cleanup migration.

## 2026-11-16

### Fixed

- Remove the retired consumer parity checker only after successful shared-source synchronization; preserve it on failed validation and reject unsafe cleanup paths before writes.

### Changed

- Fold shared release verification and synchronization into the existing bundle builder; keep CI/deployment parity gates and store the immutable Infrastructure source pin in the existing app configuration.

### Removed

- Remove the standalone release parity checker and per-application shared-source JSON file while retaining their automated checks.


## 2026-11-15

### Fixed

- Verify the CI uv bootstrap against a reviewed wheel SHA-256 before installation across all four repositories; reject unsupported runner targets and source distributions.

### Changed

- Raise the complete source-diff limit for all three AI reviewers to 2 MB (2,000,000 bytes) across all four repositories; preserve fail-closed incomplete reviews and all other context, token and model settings.

## 2026-11-14

### Changed

- Normalize historical custom Resend backend selectors to the maintained django-anymail backend in new app bundles; preserve SMTP and retained recovery artifacts (#148; FullStackTemplate #340).
- Support application `config/` and `apps/` namespaces in release tooling; normalize the known legacy Resend backend paths only when creating new bundles and retain historical recovery data (#148; FullStackTemplate #339).
- Introduce a locked uv Python 3.12 project for repository tooling; synchronize CI and local parser environments, add uv dependency updates and retain a narrow reviewed dependency-scope gate (#147).
- Point the canonical application release workflow at `backend/docker/Dockerfile` while retaining the backend build context (FullStackTemplate #337).
- Standardize README heading emojis, sentence case, reference labels and Markdown spacing while preserving substantive content, code examples and existing anchors.
- Point the canonical application release workflow at `frontend/docker/Dockerfile` while retaining the frontend build context and application-specific build arguments.
- Consolidate durable documentation into existing owning READMEs, move the active CI inventory beside workflow guidance, and repair links and architecture regressions.
- Restore consistent changelog titles, chronological dates, ordered categories, and spacing while preserving historical entries.
- Align shared agent instructions across the repository family while preserving application-specific contracts and Infrastructure authorization controls.
- Place active CI helpers under `.github/tools/`, gateway release/preflight tools under `nginx/`, and manifest maintenance under `app-release/`; update callers and owner guides.

### Removed

- Remove the unused JSON-error binding from the shared AI-review publisher while preserving unavailable-review reporting and failure gates.
- Remove the unused origin constant from the shared application bundle builder; release readiness continues to use the application domain.
- Remove the root `scripts/` folder and manual SQLite snapshot helper.
- Remove the retired cutover and MCP-retirement guides after owner review, and update remaining links to the owning READMEs and recorded decisions.
- Remove duplicate documentation indexes, redirects, stale narratives and historical receipts after preserving useful contracts. Retain the cutover and MCP-retirement operator guides for separate review.
- Remove the root `tests/` suites and fixtures for ingress, gateway transactions and retirement, SQLite snapshots, release profiles, automation policy and bounded diagnostics. Retain Compose configuration, shared release manifest validation and action-local regressions; reusable ingress/recovery outputs explicitly report the retired suites as not applicable.

## 2026-11-13

### Changed

- Standardize root ignore rules across the repository family for local environments, builds, caches, test reports, databases, and certificates; keep configuration examples and dependency lockfiles visible.
- Standardize GitHub documentation across the four repositories: setup in `.github/README.md`, workflow behavior in `.github/workflows/README.md`, and shared reviewer/action contracts in `.github/actions/README.md`.
- Document the consolidated application MCP code, source metadata, and ChatGPT package locations; gateway runtime and release policy remain unchanged ([FullStackTemplate #324](https://github.com/VanillaIceCube/FullStackTemplate/issues/324)).
- Reorganize the main README as a project introduction with folder guides; consolidate setup, API/workflow references, scripts, tests, and documentation indexes with consistent emoji headings.

### Removed

- Remove the contribution guide and pull request template; retain operational requirements in existing guides.
- Delete historical Batch 2/3 parity reports and hash snapshots; remove obsolete links without moving or consolidating documentation.

## 2026-11-12

### Added

- Start a one-hour HSTS policy on application HTTPS responses, including private and error routes, with ingress coverage and documented expiry behavior (FullStackTemplate #299).

### Fixed

- Narrow SQLite snapshot cleanup handling to subprocess failures, OS errors and explicit interruptions, preserving the original snapshot failure when cleanup also fails (#133).

### Changed

- Consolidate gateway deploy and rollback input validation. The transport helper now reports a specific error when a deploy request includes a recovery ID.

## 2026-11-11

### Fixed

- Preserve SQLite snapshot errors and interruptions when temporary-artifact cleanup fails; report the artifact and exit code or exception type without exposing subprocess output.
- Read CI reports as UTF-8 and allow gateway evidence without a configured step-summary file.

### Changed

- Upgrade the shared application build template to immutable Docker login action v4.8.0; consumers must synchronize the same Infrastructure source commit and manifest.
- Align CodeQL init/analyze at the immutable v4.39.3 revision and refresh the checked workflow architecture inventory.

### Removed

- Remove retired Jules notebooks, persona prompts and active operating instructions after the linked PRs merged and a fresh open-PR inventory passed (#117); preserve general maintenance guidance, historical evidence and independent CI/security/release controls.

## 2026-11-06

### Added

- Managed production-promotion impact summaries from the actual current target comparison, with bounded metadata, owned-comment updates and race/permission coverage.
- Source-linked Mermaid CI/CD architecture and checked per-repository workflow/action inventories, preserving application and gateway trust differences.
- Bounded, attributed human discussion context and conservative App-owned reviewer follow-ups, with adversarial, stale-head, idempotency and permission regressions.
- Safe Responses token/latency evidence, dated partial cost estimates and validated owner configuration/recovery controls; existing Luna model selection is preserved.

### Fixed

- Restore security-alert action loading by resolving repository variables in caller workflows and passing validated explicit composite inputs.
- Cover default, empty, explicit and invalid configuration plus empty/nonempty mocked alert pipelines and all three caller contracts.
- Architecture guidance no longer presents completed reviewer credential migration or obsolete test/runtime assumptions as future work.
- Reviewer ownership no longer falls back to persona-name matching; old-head verdicts are rejected and writer runs serialize.

## 2026-11-05

### Added

- Mocked composite request/history regressions and bounded early/middle/late failure evidence.
- Shared deployment parity regression for approved Action updates and unauthorized drift.
- Workflow supply-chain policy regressions.

### Fixed

- Ingress retry helper now raises explicitly after exhaustion, avoiding mixed return paths.
- Reject unverifiable malware advisory classifications before changing source checkpoints or issues.
- Recover the exact structured concurrent-close response only after verifying saved lifecycle state and body.
- Recover omitted alert refs deterministically and interrupted Project synchronization without duplicate issues or resetting planning.

### Changed

- Use the platform base commit for workflow grant authority and retain bounded diagnostic artifacts.
- Preserve the existing reporter interface and independent Infrastructure validation model.
- Source-owned deployment Action pins include readable version comments.

## 2026-11-03

### Fixed

- Collect usage evidence for every Dependabot dependency and use each major update's own versions and ecosystem for upstream release evidence.
- Preserve independent AI review findings during duplicate suppression and require valid HTTP(S) sources in major-upgrade briefs.
- Validate each release's frontend ports against its own policy so Notoli can remove IPv4 and IPv6 port 3000 through a reviewed app release (#23).

## 2026-11-02

### Fixed

- Enforce aligned immutable CodeQL entry points in the required scope gate, with split-upgrade, cross-workflow drift and mutable-pin regressions; retain owner-only merge policy.

### Changed

- Group all CodeQL action entry points in coordinated Dependabot version and security updates while preserving existing schedules and review gates ([FullStackTemplate #271](https://github.com/VanillaIceCube/FullStackTemplate/issues/271)).

## 2026-10-30

### Fixed

- Keep disabled MacroMapper MCP/discovery paths behind uncached 404 responses
  instead of falling through to the frontend during external MCP retirement.
- Allow the validated MCP client's callback origin on its consent page so Chromium
  can complete authorization, preserving exact callback and OAuth checks.

### Changed

- Route MacroMapper MCP and discovery to its app-owned backend through the same
  streaming/no-store include as Notoli; document gateway-first activation before
  the independent MCP app release, preserving existing networks and proxy trust.
- Validate enabled MacroMapper MCP origin, exact gateway trust and readiness in
  canonical release contract tests while retaining disabled generic app coverage;
  synchronize consumers through the regenerated shared-source manifest.
- Use GPT-6 Luna for all OpenAI PR reviewers and security-alert grouping while
  preserving existing review gates, isolated credentials and token budgets.
- Retire external MCP application build/runtime source, disposable experiments
  and their CI first; retain existing deployment controllers and inputs for the
  separately coordinated final cleanup (#96, #99).
- Retire the external YNAB integration and shared MCP issuer in favor of nginx
  routing to app-owned MCP/OAuth; document the ordered, main-first cleanup (#56).
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

### Added

- Define the optional multi-app MCP ingress/readiness/onboarding contract and an inactive generic vhost example, with isolated enabled/ordinary app routing checks.

### Fixed

- Fail closed on incomplete dependency reviews and retain sanitized structured evidence with a bounded RoboCop report.
- Preserve alert history and Project metadata before auto-close; verify concurrent closure without suppressing unrelated API errors and use the current Work type field.

### Changed

- Share Notoli's exact MCP transport directives through an opt-in Nginx include and apply no-store policy to discovery; keep MacroMapper's live MCP profile disabled.
- Use repository Actions settings for gateway SSH configuration, with owner/branch/source/workflow checks before credential loading and contents-read-only tokens; remove GitHub Environment policy and Deployment API dependencies.
- Record promoted versus running gateway identities in sanitized Actions summaries and the durable host journal; report runner failure/cancellation without asserting a host outcome, and document verified settings migration, cleanup and repository-secret exposure.
- Align agent/reviewer policy with the owner-selected repository-only gateway settings model, including its workflow-writer trust boundary; preserve all required reviewer gates.

## 2026-10-19

### Fixed

- Accept regular gateway promotion merge commits only when their complete Git tree matches reviewed main, while preserving exact-source and environment approval checks.

### Changed

- Require Obi-Wan, Lint Eastwood and RoboCop reviews for same-repository Dependabot PRs, matching the application/template reviewer eligibility; retain fork exclusions and manual owner merging.
- Require six reviewer secrets in both Actions and Dependabot, and derive Required CI review applicability from the PR source repository for both human and bot authors.
- Separate Obi-Wan, Lint Eastwood, and RoboCop OpenAI secrets, including RoboCop alert aggregation; pass only each reviewer's own credentials, stage `OPENAI_REVIEWERS_PROJECT_ID` independently, and document the deferred per-repository key migration.
- Standardize gateway SSH configuration on DEPLOY_* names, one private-key secret and four connection variables; derive known-host pinning only after exact fingerprint verification and retain the renamed dedicated key's identity.
- Deploy reviewed gateway source automatically when the owner promotes it to env-prod, without a second reviewer or per-release approval variable; verify original/retrying owner identity, the environment branch restriction and exact current source.
- Align repository reviewer policy with owner-authorized gateway promotion while preserving independent scans, required source reviews and explicit recovery authorization.

## 2026-10-18

### Added

- Add disabled-by-default gateway deployment from separately approved `env-prod` revisions, protected environment policy checks and pinned SSH host-key negotiation.
- Add private versioned gateway staging, exclusive maintenance locking, bounded public/origin readiness, durable interruption barriers and gateway-only rollback.
- Add promoted/running-source tracking, no-restart handling for unchanged gateway configuration, and disposable release/recovery regression coverage.
- Document operator adoption, production approval prerequisites, retry, rollback and recovery retention.
- Exercise all shared release suites for the two existing app policies and an isolated FullStackTemplate onboarding fixture.

### Fixed

- Revalidate current app identities during interrupted gateway recovery after reboot, while preserving route-network IDs and exact proxy trust.
- Preserve verified deployment success when retiring older records fails or a later runner finalizer executes.
- Keep explicit gateway rollback independent of unused candidate archive creation or transfer.
- Derive release preflight test networks and containers from app policy instead of assuming every non-Notoli consumer is MacroMapper; retain explicit existing-app trust and secret assertions.

### Changed

- Updated Nora and Marty to v3: one open PR per agent, with repeat runs maintaining the existing PR and integrating current main.

## 2026-10-11

### Added

- Add infrastructure Obi-Wan, Lint Eastwood and RoboCop reviews with tested inline publishing, prior-review history and visible failure gates.
- Add Python, JavaScript and Actions CodeQL analysis, Dependency Review, Gitleaks, actionlint/ShellCheck and explicit package scanner applicability checks.
- Add weekly Actions/Compose Dependabot updates and daily/manual security-alert issue reconciliation for Infrastructure Project #13.
- Document credentials, least-privilege tokens, scanner scope and activation acceptance.
- Add host-owned ingress Compose, Nginx routes, topology validation and the reviewed cutover/reversal guide.
- Add SQLite snapshot/restore validation including live container-local WAL, plus disposable ingress/recovery tests.
- Add versioned common app release tools, workflow template, shared deployment tests and pinned-source parity enforcement for Notoli and MacroMapper.
- Add repository contribution/agent guidance, a pull-request template, editor conventions and the owner's Modified MIT non-commercial license.

### Fixed

- Give MacroMapper backend responses a two-minute upstream read timeout so slower meal estimation can return within the companion app's 110-second AI budget.
- Verify a real delayed upstream response beyond the former 60-second proxy limit in the disposable ingress suite.
- Identify public readiness requests as `JudeAppRelease/1.0` so Cloudflare accepts the deployment client while preserving all response checks.

### Changed

- Require independent checks and applicable reviewers without auto-merge, source mutation or production workflows.
- Include all alert severities and adapt security metadata to Project #13's Work type field.
- Archive preparation chronology in coordination #4, correct approval/implementation status and clarify cutover-only snapshot ownership.
- Document the approved architecture, app-specific deployment contract and intentional parity differences.
- Align repository documentation with the emoji headings and navigation used by the application repositories.

No production changes are implied by this source release; merges and operations require separate owner approval.
