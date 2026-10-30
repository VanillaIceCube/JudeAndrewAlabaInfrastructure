"""Explicit source recipe inventory; no private files enter the Docker context."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = {"Dockerfile", ".dockerignore", "README.md", "SHARED-FRAMEWORK-LICENSE.md", "compose.yml",
       "mcp-framework-source.json", "dependency-wheels.json", "requirements.txt", "build.py",
       "run_tests.py", "run_source_tests.py", "run_container_tests.py"}


def inventory():
    files = [ROOT / name for name in TOP]
    for directory in ("backend", "issuer_tests", "scripts"):
        for path in (ROOT / directory).rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if path.is_symlink() or path.suffix not in {".py", ".html", ".json"}:
                raise ValueError("Unexpected authorization source file")
            files.append(path)
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for path in sorted(files)}


def verify():
    expected = json.loads((ROOT / "manifest.json").read_text())
    if expected != inventory():
        raise ValueError("Authorization source manifest mismatch; regenerate explicitly")
    return expected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        (ROOT / "manifest.json").write_text(json.dumps(inventory(), indent=2) + "\n", encoding="utf-8")
    else:
        verify()
        print("Authorization source manifest verified")
