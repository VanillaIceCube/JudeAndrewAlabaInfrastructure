"""Actions-side gateway transport and deployment tracking. Never print credentials."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from gateway_release import IDENTITY, SHA, ReleaseError, require, run

REPOSITORY = "VanillaIceCube/JudeAndrewAlabaInfrastructure"
ENVIRONMENT = "gateway-production"
APPROVAL_ENVIRONMENT = "gateway-approval"
REMOTE = "/opt/host-ingress-deploy/incoming/"


def api(endpoint, method="GET", data=None):
    args = ["gh", "api", "--method", method, endpoint]
    if data is not None:
        args += ["--input", "-"]
    result = subprocess.run(args, input=json.dumps(data) if data is not None else None,
                            capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, "GitHub deployment API failed")
    return json.loads(result.stdout) if result.stdout.strip() else None


def policy(environment, branches):
    require(environment.get("deployment_branch_policy") == {"protected_branches": False, "custom_branch_policies": True},
            "Production environment must use selected branches")
    require([(item["name"], item["type"]) for item in branches["branch_policies"]] == [("env-prod", "branch")],
            "Only env-prod may access production credentials")
    require(environment.get("can_admins_bypass") is False, "Disable environment protection bypass")


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
    require(os.environ.get("DEPLOY_ENABLED") == "true", "Gateway deployment is disabled")
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
    policy(api(f"repos/{REPOSITORY}/environments/{APPROVAL_ENVIRONMENT}"),
           api(f"repos/{REPOSITORY}/environments/{APPROVAL_ENVIRONMENT}/deployment-branch-policies"))
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
    key.write_text(env["DEPLOY_SSH_KEY"].replace("\r\n", "\n").rstrip("\n") + "\n")
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


def retire_previous(deployment):
    # GitHub auto_inactive explicitly excludes production deployments.
    page = 1
    while True:
        deployments = api(f"repos/{REPOSITORY}/deployments?environment={ENVIRONMENT}&per_page=100&page={page}")
        for previous in deployments:
            if previous["id"] == deployment:
                continue
            latest = api(f"repos/{REPOSITORY}/deployments/{previous['id']}/statuses?per_page=1")
            if latest and latest[0]["state"] == "success":
                status(previous["id"], "inactive", "Superseded by verified gateway deployment " + str(deployment))
        if len(deployments) < 100:
            break
        page += 1


def status(deployment, state, description):
    api(f"repos/{REPOSITORY}/deployments/{deployment}/statuses", "POST",
        {"state": state, "description": description,
         "log_url": os.environ["GITHUB_SERVER_URL"] + "/" + REPOSITORY + "/actions/runs/" + os.environ["GITHUB_RUN_ID"],
         "auto_inactive": False})
    if state == "success":
        try:
            retire_previous(deployment)
        except Exception:
            # Optional metadata cleanup cannot reclassify verified host acceptance.
            print("::warning::Gateway accepted; prior deployment retirement incomplete. Reconcile older metadata separately.")


def record_failure(deployment, description):
    latest = api(f"repos/{REPOSITORY}/deployments/{deployment}/statuses?per_page=1")
    if latest and latest[0]["state"] == "success":
        print("::warning::Preserving verified gateway success despite a later runner or metadata failure.")
    else:
        status(deployment, "failure", description)


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
    uploads = [Path("scripts/gateway_release.py"), Path("scripts/check_host.py")]
    if operation == "deploy":
        run(["git", "archive", "--format=tar", "--output=" + str(archive), source,
             "compose.yml", "nginx", "scripts/gateway_release.py", "scripts/check_host.py"])
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
    return result


def main():
    source = authorization()
    operation = os.environ.get("GATEWAY_OPERATION") or "deploy"
    recovery = os.environ.get("GATEWAY_RECOVERY", "")
    deployment = api(f"repos/{REPOSITORY}/deployments", "POST",
                     {"ref": source, "auto_merge": False, "required_contexts": [], "environment": ENVIRONMENT,
                      "production_environment": True, "description": "Gateway " + operation,
                      "payload": {"run": os.environ["GITHUB_RUN_ID"], "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
                                  "operation": operation, "recovery": recovery}})["id"]
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"deployment={deployment}\n")
    status(deployment, "pending", "Approved gateway operation queued")
    try:
        status(deployment, "in_progress", "Host transaction starting; durable host journal is authoritative")
        with tempfile.TemporaryDirectory() as temporary:
            result = execute(source, operation, recovery, Path(temporary))
        if result["status"] == "success" or (result["status"] == "unchanged" and result["running_source"] == source):
            status(deployment, "success", "Accepted running gateway " + result["running_source"])
        else:
            # An unchanged promotion/rollback must not replace the running source identity.
            status(deployment, "inactive", result["status"] + "; running gateway " + result["running_source"])
            if result["status"] == "rolled_back":
                restored = api(f"repos/{REPOSITORY}/deployments", "POST",
                               {"ref": result["running_source"], "auto_merge": False, "required_contexts": [],
                                "environment": ENVIRONMENT, "production_environment": True,
                                "description": "Verified gateway recovery",
                                "payload": {"recovery_attempt": deployment, "recovery": recovery}})["id"]
                status(restored, "success", "Verified restored gateway " + result["running_source"])
        print(json.dumps(result))
    except Exception:
        record_failure(deployment, "Operation failed/interrupted; inspect host journal before retry or recovery")
        raise


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["finalize-failure"]:
            deployment = os.environ["GATEWAY_DEPLOYMENT_ID"]
            require(deployment.isdecimal(), "Invalid deployment identity")
            record_failure(deployment, "Runner failed/cancelled; inspect durable host record before recovery")
        else:
            main()
    except (ReleaseError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise SystemExit("Gateway workflow failed; private credentials and host output withheld") from None
