"""Build an unpublished egress candidate from a reviewed, immutable recipe."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def build(tag, record):
    if not re.fullmatch(r"[a-z0-9][a-z0-9./:_-]*", tag) or record.exists():
        raise ValueError("Invalid local image tag or existing build record")
    recipe = (HERE / "Dockerfile").read_bytes().replace(b"\r\n", b"\n")
    manifest = json.loads((HERE / "manifest.json").read_text())
    if manifest != {"Dockerfile": hashlib.sha256(recipe).hexdigest()}:
        raise ValueError("Egress recipe manifest mismatch")
    # No repository files, credentials or mutable dependency resolver enter context.
    with tempfile.TemporaryDirectory(prefix="ynab-egress-build-") as directory:
        context = Path(directory)
        (context / "Dockerfile").write_bytes(recipe)
        subprocess.run(["docker", "build", "--no-cache", "--platform", "linux/amd64",
                        "-t", tag, str(context)], check=True, timeout=180)
    image_id = subprocess.check_output(["docker", "image", "inspect", tag,
                                       "--format", "{{.Id}}"], text=True).strip()
    with record.open("x", encoding="utf-8") as output:
        json.dump({"image_id": image_id, "manifest": manifest,
                   "published": False, "production_approved": False}, output, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    build(args.tag, args.record)
