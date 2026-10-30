"""Build a local unpublished candidate from an exact credential-free context."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("authorization_manifest", ROOT / "scripts/update_manifest.py")
manifest_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest_module)


def build(tag, record):
    if not re.fullmatch(r"[a-z0-9][a-z0-9./:_-]*", tag) or record.exists():
        raise ValueError("Invalid candidate tag or existing build record")
    manifest = manifest_module.verify()
    subprocess.run(["docker", "info"], check=True, capture_output=True, timeout=30)
    with tempfile.TemporaryDirectory(prefix="mcp-auth-build-") as directory:
        context = Path(directory)
        for name in manifest:
            destination = context / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / name).read_bytes().replace(b"\r\n", b"\n"))
        subprocess.run(["docker", "build", "--platform", "linux/amd64", "--no-cache", "-t", tag, str(context)],
                       check=True, timeout=240)
    image_id = subprocess.check_output(["docker", "image", "inspect", tag, "--format", "{{.Id}}"], text=True).strip()
    with record.open("x", encoding="utf-8") as output:
        json.dump({"image_id": image_id, "manifest": manifest, "published": False, "production_approved": False}, output, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    build(args.tag, args.record)
