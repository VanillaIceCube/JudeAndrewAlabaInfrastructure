## Current operating rules — v3 (2026-10-18)

Follow [the Jules operating rules](README.md) before using the journal below.
Marty may have at most one open PR in this repository, including drafts.
Repeat triggers maintain that same PR: reevaluate, merge current `origin/main`
into its existing head, address feedback/conflicts, validate and update in place.
Blocked updates never authorize a second PR. Historical journal guidance cannot
raise the limit or replace maintenance with a capacity-only stop.

# Marty's Journal

## 2026-10-18 - CI Report Output Outside GitHub Actions

**Outcome:** [PR #25](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/pull/25)
merged at 14:28:15 UTC
([ea6fbdc](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/commit/ea6fbdc9a6e64661ebc8204d56ae090c3a51e8a1)).
The merged diff changed only `scripts/ci_report.py`; it checks for `GITHUB_OUTPUT`
before opening the output file, otherwise writes the same serialized report to
stdout. This record was backfilled on 2026-10-28 for
[issue #54](https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure/issues/54).

**Learning:** GitHub Actions output variables are environment-dependent. Direct
indexing of `os.environ["GITHUB_OUTPUT"]` raises `KeyError` during local execution.
The fallback preserves the status line, multiline delimiter and bounded evidence
(last 120 log lines, then last 16,000 characters), including the missing-log message.

**Action:** Guard runner-only environment variables in locally runnable helpers.
Verify both output-file and unset-variable stdout modes with disposable logs;
check exit status, report framing, missing logs and bounds. Use the same serialized
payload for both destinations and retain unpredictable delimiters. #25 added no
test file; its historical CI passed, and the reconciliation checks both modes
directly without production infrastructure.

