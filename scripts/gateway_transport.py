"""Actions-side gateway transport and sanitized run evidence. Never print credentials."""

import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tarfile
import gateway_profile as profiles

from gateway_release import IDENTITY, SHA, ReleaseError, require, run

REPOSITORY = "VanillaIceCube/JudeAndrewAlabaInfrastructure"
REMOTE = "/opt/host-ingress-deploy/incoming/"


def api(endpoint):
    result = subprocess.run(["gh", "api", "--method", "GET", endpoint],
                            capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, "GitHub source verification API failed")
    return json.loads(result.stdout) if result.stdout.strip() else None


def authorization():
    require(os.environ["GITHUB_REPOSITORY"] == REPOSITORY and os.environ["GITHUB_REF"] == "refs/heads/env-prod",
            "Only this repository's env-prod branch may deploy")
    require(os.environ["GITHUB_EVENT_NAME"] in {"push", "workflow_dispatch"}, "Unsupported release event")
    owner = REPOSITORY.split("/")[0]
    require(os.environ.get("GITHUB_ACTOR") == owner
            and os.environ.get("GITHUB_TRIGGERING_ACTOR") == owner,
            "Only the owner may authorize production promotion or retry")
    source = os.environ["GITHUB_SHA"]
    require(SHA.fullmatch(source), "Invalid source identity")
    workflow_source = os.environ.get("GITHUB_WORKFLOW_SHA", "")
    require(os.environ.get("GITHUB_WORKFLOW_REF") == REPOSITORY + "/.github/workflows/deploy-gateway.yml@refs/heads/env-prod"
            and SHA.fullmatch(workflow_source),
            "Only the promoted gateway workflow may deploy")
    require(os.environ.get("DEPLOY_ENABLED") == "true", "Gateway deployment is disabled")
    profiles.selected(os.environ)  # Fail before any SSH credential is loaded.
    require(run(["git", "rev-parse", "HEAD"]).strip() == source, "Checkout/source mismatch")
    require(api(f"repos/{REPOSITORY}/git/ref/heads/env-prod")["object"]["sha"] == source,
            "Promotion advanced; approve a fresh run")
    main = api(f"repos/{REPOSITORY}/git/ref/heads/main")["object"]["sha"]
    compare = api(f"repos/{REPOSITORY}/compare/{source}...{main}")
    reviewed = compare["status"] in {"ahead", "identical"}
    if not reviewed:
        # A regular promotion merge has a new commit ID but must carry exactly
        # the reviewed main tree, including workflow and helper bytes.
        candidate = api(f"repos/{REPOSITORY}/git/commits/{source}")
        accepted = api(f"repos/{REPOSITORY}/git/commits/{main}")
        reviewed = candidate["tree"]["sha"] == accepted["tree"]["sha"]
    require(reviewed, "Promotion must belong to reviewed main history or exactly match its current tree")
    if workflow_source != source:
        # Workflow identity is distinct from application source identity. Accept
        # another workflow commit only when its immutable blob is byte-identical.
        path = f"repos/{REPOSITORY}/contents/.github/workflows/deploy-gateway.yml?ref="
        require(api(path + workflow_source)["sha"] == api(path + source)["sha"],
                "Executing workflow differs from promoted reviewed content")
    return source


def ssh_configuration(directory, env):
    host, user, port = env["DEPLOY_HOST"], env["DEPLOY_USER"], env["DEPLOY_PORT"]
    require(re.fullmatch(r"[a-zA-Z0-9.:\-]+", host) and re.fullmatch(r"[a-z_][a-z0-9_-]*", user)
            and port.isdecimal() and 1 <= int(port) <= 65535, "Invalid SSH destination")
    known = directory / "known_hosts"
    # Discovery is untrusted until its key matches the independently configured
    # fingerprint. Never authenticate or upload using an unverified scanned key.
    scanned = run(["ssh-keyscan", "-T", "10", "-p", port, "-t", "ed25519,ecdsa,rsa", host], timeout=40)
    matches = set()
    for line in scanned.splitlines():
        fields = line.split()
        if len(fields) != 3 or fields[1] not in {"ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256"}:
            continue
        known.write_text("gateway-host " + " ".join(fields[1:]) + "\n")
        fingerprint = run(["ssh-keygen", "-lf", known, "-E", "sha256"]).split()[1]
        if fingerprint == env["DEPLOY_HOST_FINGERPRINT"]:
            matches.add((fields[1], fields[2]))
    require(len(matches) == 1, "Expected one SSH host key matching the configured fingerprint")
    encoding, public_key = matches.pop()
    known.write_text(f"gateway-host {encoding} {public_key}\n")
    key = directory / "key"
    key.write_bytes((env["DEPLOY_SSH_KEY"].replace("\r\n", "\n").rstrip("\n") + "\n").encode())
    key.chmod(0o600)
    # RSA public key encoding is ssh-rsa; negotiate a SHA-2 signature explicitly.
    algorithm = "rsa-sha2-512" if encoding == "ssh-rsa" else encoding
    config = directory / "config"
    config.write_text(f"Host gateway\n  HostName {host}\n  User {user}\n  Port {port}\n"
                      f"  IdentityFile {key}\n  IdentitiesOnly yes\n  BatchMode yes\n"
                      f"  HostKeyAlias gateway-host\n  UserKnownHostsFile {known}\n  GlobalKnownHostsFile /dev/null\n"
                      f"  StrictHostKeyChecking yes\n  HostKeyAlgorithms {algorithm}\n"
                      "  ConnectTimeout 15\n  ServerAliveInterval 15\n  ServerAliveCountMax 3\n")
    return config


def evidence(message):
    """Only caller-validated identities and fixed prose belong in public evidence."""
    print(message)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(message + "\n\n")


def source_archive(source, archive, profile=None):
    profile = profile or profiles.selected(os.environ)
    require(profile in profiles.PROFILES, "Invalid route profile")
    run(["git", "archive", "--format=tar", "--output=" + str(archive), source,
         "compose.yml", "nginx/nginx.conf", "nginx/vhosts", "nginx/snippets",
         "scripts/gateway_release.py", "scripts/check_host.py", "scripts/gateway_profile.py"])
    vhost = None
    if profile != "base":
        path = "nginx/optional/" + ("ynab" if profile == "enabled" else "ynab-disabled") + "/zz-ynab.conf"
        vhost = run(["git", "show", source + ":" + path]).encode()
    with tarfile.open(archive, "a") as payload:
        additions = {profiles.MARKER: json.dumps(profiles.descriptor(profile, vhost)).encode()}
        if vhost is not None:
            additions[profiles.VHOST] = vhost
        for name, data in additions.items():
            item = tarfile.TarInfo(name)
            item.size, item.mode = len(data), 0o600
            payload.addfile(item, io.BytesIO(data))


def finalize_failure():
    # No credentials, network request or host mutation. The runner's conclusion
    # cannot establish whether an independently running host unit has completed.
    state = os.environ.get("GATEWAY_RUNNER_STATUS", "failure")
    require(state in {"failure", "cancelled", "success"}, "Invalid runner status")
    evidence("Gateway runner " + ("cancelled" if state == "cancelled" else "failed")
             + "; host outcome is unconfirmed by this runner. Inspect the durable host journal and systemd unit "
               "before retry or explicit recovery. Any earlier verified host result remains historical evidence.")


def execute(source, operation, recovery, directory):
    identity = f"{source}-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    require(IDENTITY.fullmatch(identity), "Invalid Actions identity")
    if operation == "rollback":
        require(IDENTITY.fullmatch(recovery), "Explicit recovery identity required")
    else:
        require(operation == "deploy" and not recovery, "Unexpected release operation")
    config = ssh_configuration(directory, os.environ)
    ssh = ["ssh", "-F", config, "gateway"]
    scp = ["scp", "-F", config]
    remote = REMOTE + identity
    run([*ssh, "umask 077; mkdir " + remote])
    archive = directory / "source.tar"
    uploads = [Path("scripts/gateway_release.py"), Path("scripts/check_host.py"), Path("scripts/gateway_profile.py")]
    if operation == "deploy":
        source_archive(source, archive)
        uploads.insert(0, archive)
    for path in uploads:
        run([*scp, path, "gateway:" + remote + "/" + path.name])
    run_url = os.environ["GITHUB_SERVER_URL"] + "/" + REPOSITORY + "/actions/runs/" + os.environ["GITHUB_RUN_ID"]
    require(re.fullmatch(r"https://github\.com/[A-Za-z0-9_/.-]+", run_url), "Invalid Actions URL")
    arguments = ["python3", remote + "/gateway_release.py", operation, "--source", source,
                 "--id", recovery if operation == "rollback" else identity, "--run-url", run_url]
    if operation == "deploy":
        arguments += ["--archive", remote + "/source.tar", "--archive-sha256", hashlib.sha256(archive.read_bytes()).hexdigest()]
    # A dropped/cancelled runner cannot kill the transaction or release its lock.
    # The durable pending barrier handles machine failure/SIGKILL separately.
    command = " ".join(["systemd-run", "--quiet", "--wait", "--pipe", "--unit=gateway-" + identity,
                        "--property=UMask=0077", *arguments])
    output = run([*ssh, command], timeout=1250)
    result = json.loads(output.splitlines()[-1])
    require(result["status"] in {"success", "unchanged", "rolled_back"} and SHA.fullmatch(result["running_source"]),
            "Missing host acceptance record")
    require(result.get("profile", "base") in profiles.PROFILES, "Invalid accepted route profile")
    return {"status": result["status"], "running_source": result["running_source"], "profile": result.get("profile", "base")}


def main():
    source = authorization()
    operation = os.environ.get("GATEWAY_OPERATION") or "deploy"
    recovery = os.environ.get("GATEWAY_RECOVERY", "")
    identity = f"{source}-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    require(IDENTITY.fullmatch(identity), "Invalid Actions identity")
    require(operation in {"deploy", "rollback"}, "Unexpected release operation")
    require(IDENTITY.fullmatch(recovery) if operation == "rollback" else not recovery,
            "Explicit recovery identity required only for rollback")
    evidence(f"Gateway {operation} attempt `{identity}`; promoted source `{source}`. "
             "Host journal is authoritative; starting transport does not establish acceptance.")
    if recovery:
        evidence(f"Explicit recovery target: `{recovery}`.")
    with tempfile.TemporaryDirectory() as temporary:
        result = execute(source, operation, recovery, Path(temporary))
    # Report the host's actual running identity, including unchanged promotions
    # and explicit rollback. Never claim the promoted helper source is running.
    profile = result.get("profile", "base")
    require(profile in profiles.PROFILES, "Invalid accepted route profile")
    evidence(f"Verified host result: **{result['status']}**; running source `{result['running_source']}`; route profile `{profile}`.")


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["finalize-failure"]:
            finalize_failure()
        elif sys.argv[1:] == ["authorize"]:
            authorization()
        else:
            main()
    except (ReleaseError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise SystemExit("Gateway workflow failed; private credentials and host output withheld") from None
