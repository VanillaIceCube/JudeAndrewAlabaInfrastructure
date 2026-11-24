const { execFileSync } = require("node:child_process");
const test = require("node:test");

test("uv tooling scope allows the reviewed parser graph and rejects expanded dependency graphs", () => {
  const program = String.raw`
from pathlib import Path
import tempfile
from types import SimpleNamespace
import yaml

workflow = Path(".github/workflows/gate-malware.yml")
definition = yaml.safe_load(workflow.read_text(encoding="utf-8"))
steps = definition["jobs"]["scope"]["steps"]
scope_step = next(step for step in steps if step.get("id") == "scope")
command, source = scope_step["run"].split("\n", 1)
assert command == "python3 - <<'PY'" and source.endswith("\nPY\n")
namespace = {"__name__": "scope"}
exec(compile(source.removesuffix("\nPY\n"), str(workflow), "exec"), namespace)
scope = SimpleNamespace(**namespace)
assert scope.unsupported_manifests(["pyproject.toml", "uv.lock"]) == []
assert scope.unsupported_manifests(["app/uv.lock", "package.json", "requirements.txt"]) == ["app/uv.lock", "package.json", "requirements.txt"]
scope.validate_tooling_project(Path.cwd())
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    for name in scope.TOOLING_FILES:
        (root / name).write_bytes(Path(name).read_bytes())
    project = (root / "pyproject.toml").read_text()
    (root / "pyproject.toml").write_text(project.replace("PyYAML", "pyyaml"))
    scope.validate_tooling_project(root)
    (root / "pyproject.toml").write_text(project.replace("dependencies = []", 'dependencies = ["unexpected==1.0"]'))
    try:
        scope.validate_tooling_project(root)
    except ValueError:
        pass
    else:
        raise AssertionError("Runtime dependency expansion bypassed scanner review")
    (root / "pyproject.toml").write_text(project)
    lock = (root / "uv.lock").read_text()
    (root / "uv.lock").write_text(lock + '\n[[package]]\nname = "unexpected"\nversion = "1.0"\n')
    try:
        scope.validate_tooling_project(root)
    except ValueError:
        pass
    else:
        raise AssertionError("Locked graph expansion bypassed scanner review")
`;
  execFileSync(process.platform === "win32" ? "python" : "python3", ["-c", program], { stdio: "pipe" });
});

test("test gate scopes checks independently and fails closed if detection is incomplete", () => {
  const program = String.raw`
from fnmatch import fnmatchcase
import os
from pathlib import Path
import subprocess
import tempfile
import yaml

path = Path(".github/workflows/gate-test.yml")
definition = yaml.safe_load(path.read_text(encoding="utf-8"))
steps = definition["jobs"]["validate"]["steps"]
by_id = {step["id"]: step for step in steps if "id" in step}
filters = yaml.safe_load(by_id["filter"]["with"]["filters"])
for filename, expected in {
    "CHANGELOG.md": set(),
    "compose.yml": {"compose"},
    "nginx/vhosts/example.conf": {"compose"},
    "app-release/v1/workflow.yml": {"manifest"},
    ".github/actions/example/action.yml": {"automation"},
    "uv.lock": {"manifest", "automation"},
    ".github/workflows/gate-test.yml": {"compose", "manifest", "automation"},
    ".github/workflows/ci-orchestrator.yml": {"compose", "manifest", "automation"},
}.items():
    actual = {name for name, patterns in filters.items() if any(fnmatchcase(filename, pattern) for pattern in patterns)}
    assert actual == expected, (filename, actual, expected)

bash = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else "bash"
with tempfile.TemporaryDirectory() as directory:
    output = Path(directory) / "output"
    env = {**os.environ, "GITHUB_OUTPUT": output.as_posix(), "GITHUB_STEP_SUMMARY": output.as_posix()}
    def run(step, **values):
        return subprocess.run([bash, "-e", "-s"], input=by_id[step]["run"],
                              text=True, capture_output=True, env={**env, **values})

    assert run("scope", OUTCOME="success", COMPOSE="false", MANIFEST="false", AUTOMATION="false").returncode == 0
    assert run("scope", OUTCOME="failure", COMPOSE="false", MANIFEST="false", AUTOMATION="false").returncode != 0
    assert run("scope", OUTCOME="success", COMPOSE="false", MANIFEST="", AUTOMATION="false").returncode != 0

    for scope, applicable, outcome, expected in [
        ("success", "false", "skipped", "not-applicable"),
        ("failure", "", "skipped", "failure"),
        ("success", "true", "skipped", "failure"),
    ]:
        output.write_text("", encoding="utf-8")
        run("automation-report", SCOPE=scope, AUTOMATION=applicable, OUTCOME=outcome).check_returncode()
        assert output.read_text(encoding="utf-8").startswith(f"automation_status={expected}\n")
`;
  execFileSync(process.platform === "win32" ? "python" : "python3", ["-c", program], { stdio: "pipe" });
});
