"""Bounded local/CI daemon fixture with exact-run cleanup; never a deployment."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid
import build as builder

ROOT = Path(__file__).resolve().parents[2]
LABEL = "infrastructure.ynab.gateway.fixture"


def run(command, **kwargs):
    return subprocess.run(command, check=True, timeout=240, **kwargs)


def cleanup(identity):
    if not re.fullmatch(r"ynab-gateway-test-[a-f0-9]{32}", identity):
        raise ValueError("Invalid fixture identity")
    containers = subprocess.check_output(["docker", "ps", "-aq", "--filter",
                                          "label=" + LABEL + "=" + identity], text=True).split()
    if containers:
        subprocess.run(["docker", "rm", "-f", *containers], check=False, timeout=30)
    subprocess.run(["docker", "image", "rm", identity + ":fixture"], check=False, timeout=30)


def main(identity):
    if not re.fullmatch(r"ynab-gateway-test-[a-f0-9]{32}", identity):
        raise ValueError("Invalid fixture identity")
    image = identity + ":fixture"
    try:
        with tempfile.TemporaryDirectory(prefix=identity) as temp:
            builder.build(image, Path(temp) / "record.json")
            run(["docker", "run", "--rm", "--label", LABEL + "=" + identity,
                 "--network", "none", "--read-only", "--cap-drop", "ALL",
                 "--security-opt", "no-new-privileges", "--pids-limit", "64",
                 "--memory", "512m", "--cpus", "0.5", "--tmpfs",
                 "/tmp:rw,noexec,nosuid,size=32m,uid=65532,gid=65532,mode=0700",
                 "--mount", "type=bind,source=" + str(ROOT) + ",target=/workspace,readonly",
                 "-e", "PYTHONPATH=/gateway:/opt/gateway-deps", "--entrypoint", "/usr/local/bin/python",
                 image, "-P", "/workspace/services/ynab-gateway/test_gateway.py"])
            # Docker inspect is configuration evidence, not full image scanning.
            config = json.loads(subprocess.check_output(["docker", "image", "inspect", image], text=True))[0]["Config"]
            if config["User"] != "65532:65532" or config.get("ExposedPorts"):
                raise ValueError("Unexpected gateway image privilege/port configuration")
    finally:
        cleanup(identity)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup")
    args = parser.parse_args()
    if args.cleanup:
        cleanup(args.cleanup)
    else:
        main(os.environ.get("YNAB_GATEWAY_TEST_ID", "ynab-gateway-test-" + uuid.uuid4().hex))
