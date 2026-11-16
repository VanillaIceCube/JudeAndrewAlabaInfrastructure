"""Allow the reviewed uv tooling graph and fail closed on other package graphs."""
from pathlib import Path
import os
import re
import subprocess
import tomllib

PACKAGE_FILES = {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                 "requirements.txt", "pyproject.toml", "Pipfile", "Pipfile.lock", "poetry.lock",
                 "uv.lock", "Gemfile", "go.mod", "Cargo.toml", "composer.json"}
TOOLING_FILES = {"pyproject.toml", "uv.lock"}


def unsupported_manifests(paths):
    return sorted(path for path in paths if path not in TOOLING_FILES and
                  (Path(path).name in PACKAGE_FILES or
                   Path(path).name.startswith("requirements") and Path(path).suffix in {".txt", ".in"}))


def validate_tooling_project(root):
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    groups = project.get("dependency-groups", {})
    dev = groups.get("dev", [])
    if (project.get("project", {}).get("dependencies") != [] or
            set(groups) != {"dev"} or len(dev) != 1 or
            not isinstance(dev[0], str) or not re.fullmatch(r"PyYAML==[0-9][a-zA-Z0-9.+-]*", dev[0], re.IGNORECASE) or
            project.get("tool", {}).get("uv", {}).get("package") is not False or
            "build-system" in project):
        raise ValueError("Review scanner coverage before expanding the PyYAML-only tooling project")
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    packages = lock.get("package", [])
    if {package["name"] for package in packages} != {"infrastructure-tooling", "pyyaml"} or len(packages) != 2:
        raise ValueError("Review scanner coverage before expanding the locked tooling graph")


def main():
    paths = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"], text=True).splitlines()
    unsupported = unsupported_manifests(paths)
    if unsupported:
        raise SystemExit("Package scanner setup required before adding manifests: " + ", ".join(unsupported))
    validate_tooling_project(Path.cwd())
    report = ("The reviewed root uv tooling graph contains only pinned PyYAML. Dependency Review and "
              "CodeQL cover applicable dependency advisories and source; Python package malware scanning "
              "is not configured. The scope guard rejects other manifests or an expanded tooling graph. "
              "Nginx/Compose and Docker image malware/advisories require separate image/operator review.")
    print(report)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write("report=" + report + "\n")


if __name__ == "__main__":
    main()
