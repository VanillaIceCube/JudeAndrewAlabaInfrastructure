"""Actions-side gateway transport and sanitized run evidence. Never print credentials."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from gateway_release import IDENTITY, SHA, ReleaseError, require, run

repository = "VanillaIceCube/infrastructure"
REMOTE = "/opt/host-ingress-deploy/incoming/"


def authorization():
    # Only the GitHub CLI needs the API token.
    token = os.environ.pop("GH_TOKEN")

    def api(endpoint):
        result = subprocess.run(
            ["gh", "api", "--method", "GET", endpoint],
            env={**os.environ, "GH_TOKEN": token},
            capture_output=True,
            text=True,
            timeout=30,
        )
        require(result.returncode == 0, "GitHub source verification API failed")
        return json.loads(result.stdout) if result.stdout.strip() else None

    require(
        os.environ["GITHUB_REPOSITORY"] == repository
        and os.environ["GITHUB_REF"] == "refs/heads/env-prod",
        "Only this repository's env-prod branch may deploy",
    )
    require(
        os.environ["GITHUB_EVENT_NAME"] in {"push", "workflow_dispatch"},
        "Unsupported release event",
    )
    owner = repository.split("/")[0]
    require(
        os.environ.get("GITHUB_ACTOR") == owner
        and os.environ.get("GITHUB_TRIGGERING_ACTOR") == owner,
        "Only the owner may authorize production promotion or retry",
    )
    source = os.environ["GITHUB_SHA"]
    require(SHA.fullmatch(source), "Invalid source identity")
    workflow_source = os.environ.get("GITHUB_WORKFLOW_SHA", "")
    require(
        os.environ.get("GITHUB_WORKFLOW_REF")
        == repository + "/.github/workflows/deploy-gateway.yml@refs/heads/env-prod"
        and SHA.fullmatch(workflow_source),
        "Only the promoted gateway workflow may deploy",
    )
    require(
        os.environ.get("DEPLOY_ENABLED") == "true", "Gateway deployment is disabled"
    )
    require(
        run(["git", "rev-parse", "HEAD"]).strip() == source, "Checkout/source mismatch"
    )
    require(
        api(f"repos/{repository}/git/ref/heads/env-prod")["object"]["sha"] == source,
        "Promotion advanced; approve a fresh run",
    )
    main = api(f"repos/{repository}/git/ref/heads/main")["object"]["sha"]
    compare = api(f"repos/{repository}/compare/{source}...{main}")
    reviewed = compare["status"] in {"ahead", "identical"}
    if not reviewed:
        # A regular promotion merge has a new commit ID but must carry exactly
        # the reviewed main tree, including workflow and helper bytes.
        candidate = api(f"repos/{repository}/git/commits/{source}")
        accepted = api(f"repos/{repository}/git/commits/{main}")
        reviewed = candidate["tree"]["sha"] == accepted["tree"]["sha"]
    require(
        reviewed,
        "Promotion must belong to reviewed main history or exactly match its current tree",
    )
    if workflow_source != source:
        # Workflow identity is distinct from application source identity. Accept
        # another workflow commit only when its immutable blob is byte-identical.
        path = f"repos/{repository}/contents/.github/workflows/deploy-gateway.yml?ref="
        require(
            api(path + workflow_source)["sha"] == api(path + source)["sha"],
            "Executing workflow differs from promoted reviewed content",
        )
    return source


def ssh_configuration(directory, env, private_key):
    host, user, port = env["DEPLOY_HOST"], env["DEPLOY_USER"], env["DEPLOY_PORT"]
    require(
        re.fullmatch(r"[a-zA-Z0-9.:\-]+", host)
        and re.fullmatch(r"[a-z_][a-z0-9_-]*", user)
        and port.isdecimal()
        and 1 <= int(port) <= 65535,
        "Invalid SSH destination",
    )
    known = directory / "known_hosts"
    # Discovery is untrusted until its key matches the independently configured
    # fingerprint. Never authenticate or upload using an unverified scanned key.
    scanned = run(
        ["ssh-keyscan", "-T", "10", "-p", port, "-t", "ed25519,ecdsa,rsa", host],
        timeout=40,
    )
    matches = set()
    for line in scanned.splitlines():
        fields = line.split()
        if len(fields) != 3 or fields[1] not in {
            "ssh-ed25519",
            "ssh-rsa",
            "ecdsa-sha2-nistp256",
        }:
            continue
        known.write_text("gateway-host " + " ".join(fields[1:]) + "\n")
        fingerprint = run(["ssh-keygen", "-lf", known, "-E", "sha256"]).split()[1]
        if fingerprint == env["DEPLOY_HOST_FINGERPRINT"]:
            matches.add((fields[1], fields[2]))
    require(
        len(matches) == 1,
        "Expected one SSH host key matching the configured fingerprint",
    )
    encoding, public_key = matches.pop()
    known.write_text(f"gateway-host {encoding} {public_key}\n")
    key = directory / "key"
    key.write_bytes((private_key.replace("\r\n", "\n").rstrip("\n") + "\n").encode())
    key.chmod(0o600)
    # RSA public key encoding is ssh-rsa; negotiate a SHA-2 signature explicitly.
    algorithm = "rsa-sha2-512" if encoding == "ssh-rsa" else encoding
    config = directory / "config"
    config.write_text(
        f"Host gateway\n  HostName {host}\n  User {user}\n  Port {port}\n"
        f"  IdentityFile {key}\n  IdentitiesOnly yes\n  BatchMode yes\n"
        f"  HostKeyAlias gateway-host\n  UserKnownHostsFile {known}\n  GlobalKnownHostsFile /dev/null\n"
        f"  StrictHostKeyChecking yes\n  HostKeyAlgorithms {algorithm}\n"
        "  ConnectTimeout 15\n  ServerAliveInterval 15\n  ServerAliveCountMax 3\n"
    )
    return config


def evidence(message):
    """Only caller-validated identities and fixed prose belong in public evidence."""
    print(message)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write(message + "\n\n")


def main():
    # Child commands inherit the process environment. SSH reads its key from a file.
    private_key = os.environ.pop("DEPLOY_SSH_KEY", None)
    if sys.argv[1:] not in ([], ["authorize"]):
        raise ReleaseError("Unexpected gateway transport argument")
    source = authorization()
    if sys.argv[1:]:
        return
    require(private_key, "Missing deployment SSH key")
    identity = (
        f"{source}-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    )
    require(IDENTITY.fullmatch(identity), "Invalid Actions identity")
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        config = ssh_configuration(directory, os.environ, private_key)
        ssh = ["ssh", "-F", config, "gateway"]
        remote = REMOTE + identity
        run([*ssh, "umask 077; mkdir " + remote])
        archive = directory / "source.tar"
        run(
            [
                "git",
                "archive",
                "--format=tar",
                "--output=" + str(archive),
                source,
                "compose.yml",
                "gateway/nginx",
            ]
        )
        run(
            [
                "scp",
                "-F",
                config,
                archive,
                "gateway/scripts/gateway_release.py",
                "gateway/scripts/check_host.py",
                "gateway:" + remote + "/",
            ]
        )
        # Keep the lock on the host for the full launch, even if the SSH runner disconnects.
        command = " ".join(
            [
                "systemd-run",
                "--quiet",
                "--wait",
                "--pipe",
                "--unit=gateway-" + identity,
                "--property=UMask=0077",
                "python3",
                remote + "/gateway_release.py",
                "--id",
                identity,
                "--archive",
                remote + "/source.tar",
                "--archive-sha256",
                hashlib.sha256(archive.read_bytes()).hexdigest(),
            ]
        )
        output = run([*ssh, command], timeout=1250)
        require(
            output.strip().endswith("Gateway launched " + identity),
            "Host did not confirm the launch",
        )
    evidence(f"Gateway launched from reviewed source `{source}`.")


if __name__ == "__main__":
    try:
        main()
    except (
        ReleaseError,
        OSError,
        ValueError,
        KeyError,
        subprocess.SubprocessError,
    ) as error:
        detail = str(error) if isinstance(error, ReleaseError) else type(error).__name__
        raise SystemExit("Gateway workflow failed: " + detail) from None
