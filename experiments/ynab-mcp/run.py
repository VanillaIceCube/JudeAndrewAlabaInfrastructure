"""Disposable #57 experiment; never builds or deploys a production service."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
PINS = json.loads((HERE / "pins.json").read_text())


def run(args, cwd, env):
    subprocess.run(args, cwd=cwd, env=env, check=True, timeout=180)


def verify(path, pin):
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()
    if sha != pin["commit"]:
        raise ValueError("Source commit does not match reviewed pin")
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--"], cwd=path, check=True)
    lock = hashlib.sha256((path / "package-lock.json").read_bytes()).hexdigest()
    if lock != pin["lock_sha256"]:
        raise ValueError("Upstream lockfile does not match reviewed pin")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    # Do not pass the operator's credentials, agent config, NODE_OPTIONS, or npm
    # configuration to the gateway/child. HOME is a disposable fixture directory.
    with tempfile.TemporaryDirectory(prefix="ynab-mcp-poc-") as tmp:
        root = Path(tmp)
        env = {k: v for k, v in os.environ.items()
               if k.upper() in {"PATH", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP"}}
        env.update(HOME=tmp, USERPROFILE=tmp, npm_config_cache=str(root / "npm-cache"),
                   npm_config_userconfig=str(root / "empty-npmrc"))
        (root / "empty-npmrc").write_text("")
        node = shutil.which("node")
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if not node or not npm:
            raise RuntimeError("Node 24 and npm are required")
        major = int(subprocess.check_output([node, "-p", "process.versions.node.split('.')[0]"], text=True))
        if major != 24:
            raise RuntimeError("Use Node 24, matching Infrastructure CI")
        sources = []
        for name, pin in PINS.items():
            path = root / name
            run(["git", "-c", "core.autocrlf=false", "clone", "--quiet", "--no-checkout",
                 pin["repository"], str(path)], root, env)
            # Apply the override to checkout too: clone --no-checkout does not
            # persist -c, and Windows CRLF conversion would change the lock hash.
            run(["git", "-c", "core.autocrlf=false", "checkout", "--quiet", "--detach", pin["commit"]], path, env)
            verify(path, pin)
            run([npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund"], path, env)
            if name == "gateway":
                run([node, "node_modules/typescript/bin/tsc", "-p", "tsconfig.build.json"], path, env)
            sources.append(str(path))
        env.update(POC_GATEWAY_SOURCE=sources[0], POC_YNAB_SOURCE=sources[1])
        run([node, "--test", "--test-concurrency=1", str(HERE / "contract.test.mjs")], root, env)


if __name__ == "__main__":
    main()
