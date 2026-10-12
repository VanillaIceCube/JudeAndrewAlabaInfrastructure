"""Fail closed when package manifests appear without a reviewed scanner setup."""
from pathlib import Path
import os
import subprocess

PACKAGE_FILES = {"package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                 "requirements.txt", "pyproject.toml", "Pipfile", "Pipfile.lock", "poetry.lock",
                 "uv.lock", "Gemfile", "go.mod", "Cargo.toml", "composer.json"}


def unsupported_manifests(paths):
    return sorted(path for path in paths if Path(path).name in PACKAGE_FILES
                  or Path(path).name.startswith("requirements") and Path(path).suffix == ".txt")


def main():
    paths = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    unsupported = unsupported_manifests(paths)
    if unsupported:
        raise SystemExit("Package scanner setup required before adding manifests: " + ", ".join(unsupported))
    report = ("No npm/pip or other package manifests are tracked. Package malware scanning is not applicable; "
              "Nginx and Compose are not package malware scan targets. Actions changes receive Dependency Review, "
              "CodeQL Actions analysis and immutable-action policy checks. Docker image advisories require "
              "image scanning/operator review; this check does not claim container malware coverage.")
    print(report)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write("report=" + report + "\n")


if __name__ == "__main__":
    main()
