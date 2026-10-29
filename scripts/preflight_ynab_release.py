"""Mandatory paired artifact prerequisite for a future authorized YNAB release.

No container is started, image pulled/published, credential installed or network
changed. The release transaction must call this under its locks immediately
before mutation; no saved JSON approval or single-image evidence is accepted.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import uuid

from check_ynab_image_audit import AuditError, DIGEST, audit, require

PREFIX = "ghcr.io/vanillaicecube/judeandrewalabainfrastructure-ynab-"


def docker(*arguments):
    try:
        result = subprocess.run(["docker", *map(str, arguments)], capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AuditError("Local artifact operation unavailable or timed out") from error
    require(result.returncode == 0, "Local artifact operation failed")
    return result.stdout


def inspect(reference, role):
    require(role in {"gateway", "egress"} and re.fullmatch(
        re.escape(PREFIX + role + "@") + r"sha256:[a-f0-9]{64}", reference),
        "Expected role-specific immutable registry reference")
    images = json.loads(docker("image", "inspect", reference))
    require(isinstance(images, list) and len(images) == 1, "Missing exact local image")
    image = images[0]
    require(reference in image.get("RepoDigests", []) and DIGEST.fullmatch(image.get("Id", "")) and
            image.get("Os") == "linux" and image.get("Architecture") == "amd64", "Local registry identity mismatch")
    return image["Id"]


def preflight(images, scanner, cache):
    require(isinstance(images, dict) and set(images) == {"gateway", "egress"},
            "Both gateway and egress images are mandatory")
    require(os.name == "posix", "Use the disposable Linux release preflight")
    # Resolve BOTH immutable local artifacts before exporting or scanning either.
    identities = {role: inspect(reference, role) for role, reference in images.items()}
    checked = {}
    for role in ("gateway", "egress"):
        with tempfile.TemporaryDirectory(prefix="ynab-release-artifact-") as directory:
            work = Path(directory)
            archive, filesystem = work / "image.tar", work / "filesystem.tar"
            name = "ynab-audit-" + uuid.uuid4().hex
            created = False
            try:
                docker("image", "save", "--output", archive, identities[role])
                docker("create", "--pull", "never", "--name", name, "--network", "none",
                       "--entrypoint", "/bin/false", identities[role])
                created = True
                container = json.loads(docker("container", "inspect", name))[0]
                require(container.get("Image") == identities[role] and
                        container.get("State", {}).get("Status") == "created", "Filesystem image binding mismatch")
                docker("container", "export", "--output", filesystem, name)
                audit(archive, filesystem, identities[role], role, scanner, cache)
                checked[role] = {"reference": images[role], "image_id": identities[role]}
            finally:
                if created:
                    docker("container", "rm", "-v", name)
    # Returned only after two fresh scans in this invocation. Never load this
    # result from an operator-edited file as an alternative to running the gate.
    return checked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--egress", required=True)
    parser.add_argument("--scanner", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        preflight({"gateway": args.gateway, "egress": args.egress}, args.scanner, args.cache)
    except (AuditError, OSError, ValueError, KeyError, TypeError, AttributeError, tarfile.TarError):
        raise SystemExit("YNAB paired artifact preflight blocked; inspect private evidence")
    print("Both YNAB artifact prerequisites passed; deployment remains separately gated")


if __name__ == "__main__":
    main()
