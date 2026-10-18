# 📝 Changelog

## 2026-10-18

### Added
- Exercise all shared release suites for the two existing app policies and an isolated FullStackTemplate onboarding fixture.

### Fixed
- Derive release preflight test networks and containers from app policy instead of assuming every non-Notoli consumer is MacroMapper; retain explicit existing-app trust and secret assertions.

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
