# Shared GitHub actions

| Action | What it does |
| --- | --- |
| [review-dependencies](review-dependencies/action.yml) | Runs GitHub Dependency Review at the shared severity threshold and reports the evidence for RoboCop. |
| [setup-uv](setup-uv/action.yml) | Installs the reviewed uv wheel and exposes the locked Python environment to subsequent steps. |
| [setup-lint-bot](setup-lint-bot/action.yml) | Configures the Lint Eastwood identity for an eligible application lint fix. |
| [verify-branch-rules](verify-branch-rules/action.yml) | Checks the branch rules and native auto-merge API using the read-only workflow token. |

## Authoring an action

1. Give the directory a lower-case, hyphenated name. Put its public interface in `action.yml`.
2. Keep parameter mapping, step order and short commands in YAML. Name the primary JavaScript file after its directory, as in `setup-uv/setup-uv.js`. Give secondary modules names that describe their role. Invoke action programs through `GITHUB_ACTION_PATH` so a caller can choose its working directory.
3. Declare credential inputs explicitly. Each step receives the token for its operation. A review workflow that inspects a proposed change keeps privileged API calls separate from code supplied by that change.
4. Put isolated tests in [unit](../tests/unit) and tests that exercise components together in [integration](../tests/integration). Name the suite after its implementation, as in [verify-branch-rules.test.js](../tests/unit/verify-branch-rules.test.js). Keep sample API responses and expected output in [fixtures](../tests/fixtures). Run the [automation checks](../workflows/README.md#-checks-and-diagnostics) from the repository root.

## 🐍 Python toolchain bootstrap

[setup-uv.js](setup-uv/setup-uv.js) pins the Linux x64 wheel version and SHA-256. Pip requires that exact hash, accepts only wheels and installs no dependencies. Review the wheel version and hash together. The project directory defaults to `backend`. Infrastructure passes `.` for its own tooling and `subject/backend` in shared application jobs. The `only-dev` input selects the locked development tools for automation jobs.

The three reviewers and RoboCop alert feeds use [AgentHub’s action contracts](https://github.com/VanillaIceCube/agent-hub/tree/main/.github/actions).
