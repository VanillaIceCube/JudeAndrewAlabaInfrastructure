const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const test = require("node:test");

test("uv tooling scope allows the reviewed parser graph and rejects expanded dependency graphs", () => {
  const program = String.raw`
import importlib.util
from pathlib import Path
import tempfile
spec = importlib.util.spec_from_file_location("scope", ".github/tools/check_dependency_scope.py")
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)
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
