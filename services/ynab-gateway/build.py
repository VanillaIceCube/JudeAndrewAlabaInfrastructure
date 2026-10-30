"""Local-only gateway build, reusing #58's verified unchanged upstream source."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
RUNTIME = HERE.parent / "ynab-mcp"
spec = importlib.util.spec_from_file_location("ynab_runtime_build", RUNTIME / "build.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def build(tag, record):
    if not re.fullmatch(r"[a-z0-9][a-z0-9./:_-]*", tag) or record.exists():
        raise ValueError("Invalid tag or existing build record")
    manifest = json.loads((HERE / "manifest.json").read_text())
    for name, expected in manifest.items():
        if name not in {"Dockerfile", "gateway.py", "requirements.txt"}:
            raise ValueError("Unexpected gateway manifest entry")
        data = (HERE / name).read_bytes().replace(b"\r\n", b"\n")
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Gateway source manifest mismatch")
    if set(manifest) != {"Dockerfile", "gateway.py", "requirements.txt"}:
        raise ValueError("Incomplete gateway manifest")
    runtime.validate_recipe((RUNTIME / "Dockerfile").read_text())
    policy = (RUNTIME / "entrypoint.mjs").read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(policy).hexdigest() != runtime.PIN["entrypoint_sha256"]:
        raise ValueError("Upstream policy manifest mismatch")
    with tempfile.TemporaryDirectory(prefix="ynab-gateway-build-") as temp:
        source = runtime.prepare(Path(temp))
        subprocess.run(["docker", "build", "--no-cache", "--platform", "linux/amd64",
                        "--build-context", "upstream=" + str(source), "--build-context",
                        "runtime-policy=" + str(RUNTIME), "-t", tag, str(HERE)], check=True, timeout=240)
    image_id = subprocess.check_output(["docker", "image", "inspect", tag,
                                       "--format", "{{.Id}}"], text=True).strip()
    with record.open("x", encoding="utf-8") as output:
        json.dump({"image_id": image_id, "upstream": runtime.PIN["commit"],
                   "manifest": manifest, "published": False, "production_approved": False}, output, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    build(args.tag, args.record)
