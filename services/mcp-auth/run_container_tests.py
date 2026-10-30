"""Disposable local/CI Linux fixture; never contacts a provider or deploys an app."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

import build as builder

ROOT = Path(__file__).resolve().parent
LABEL = "infrastructure.mcp.auth.fixture"


def run(command, **kwargs):
    return subprocess.run(command, check=True, timeout=240, **kwargs)


def daemon_guard():
    context = subprocess.check_output(["docker", "context", "show"], text=True).strip()
    name = subprocess.check_output(["docker", "info", "--format", "{{.Name}}"], text=True).strip()
    desktop = context == "desktop-linux" and name == "docker-desktop" and not os.environ.get("DOCKER_HOST")
    ci = os.environ.get("CI") == "true" and context == "default" and not os.environ.get("DOCKER_HOST")
    if not (desktop or ci):
        raise ValueError("An isolated Docker Desktop or local CI daemon is required")


def validate_identity(identity):
    if not re.fullmatch(r"mcp-auth-test-[a-f0-9]{32}", identity):
        raise ValueError("Invalid fixture identity")


def cleanup(identity):
    validate_identity(identity)
    daemon_guard()
    containers = subprocess.check_output(["docker", "ps", "-aq", "--filter", "label=" + LABEL + "=" + identity], text=True).split()
    if containers:
        subprocess.run(["docker", "rm", "-f", *containers], check=False, timeout=30, capture_output=True)
    for suffix in ("-secrets", "-data"):
        subprocess.run(["docker", "volume", "rm", identity + suffix], check=False, timeout=30, capture_output=True)
    subprocess.run(["docker", "image", "rm", identity + ":fixture"], check=False, timeout=30, capture_output=True)


PREPARE = """
from pathlib import Path
import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
os.umask(0o077)
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
values={'django_secret_key':'synthetic-django-secret-key-for-disposable-Linux-fixture-'+('x'*40),
        'bootstrap_password':'synthetic-owner-password-only-for-fixture-9741',
        'signing_key.pem':key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()}
for name,value in values.items():
    path=Path('/run/secrets')/name
    path.write_text(value); path.chmod(0o400); os.chown(path,65532,65532)
root=Path('/data'); root.chmod(0o700); os.chown(root,65532,65532)
print('Synthetic private fixture prepared')
"""

VERIFY_STATE = """
from pathlib import Path
import os,stat
root=Path('/data')
assert stat.S_IMODE(root.stat().st_mode)==0o700 and root.stat().st_uid==65532
for path in root.iterdir():
    assert path.is_file() and path.stat().st_uid==65532 and stat.S_IMODE(path.stat().st_mode)&0o077==0
for name in ('django_secret_key','signing_key.pem','bootstrap_password'):
    path=Path('/run/secrets')/name
    assert path.stat().st_uid==65532 and stat.S_IMODE(path.stat().st_mode)==0o400
print('SQLite and synthetic private-file ownership/modes verified')
"""

PROBE = """
import json,time,urllib.request,urllib.error
def request(path,forwarded=False):
    headers={'Host':'auth.judeandrewalaba.com'}
    if forwarded: headers['X-Forwarded-Proto']='https'
    req=urllib.request.Request('http://127.0.0.1:8000'+path,headers=headers)
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs): return None
    try: response=urllib.request.build_opener(NoRedirect).open(req,timeout=3)
    except urllib.error.HTTPError as error: response=error
    return response.status,response.read()
for attempt in range(150):
    try:
        if request('/health/ready')[0]==200: break
    except (OSError,urllib.error.URLError): pass
    time.sleep(0.2)
else: raise SystemExit('Production entrypoint readiness failed')
assert request('/health/live')[0]==200
assert request('/.well-known/oauth-authorization-server')[0]==301
status,body=request('/.well-known/oauth-authorization-server',True)
assert status==200 and json.loads(body)['issuer']=='https://auth.judeandrewalaba.com'
assert request('/accounts/login/',True)[0]==200
print('Production entrypoint readiness, TLS redirect, exact proxy and login verified')
"""


def main(identity):
    validate_identity(identity)
    daemon_guard()
    run([sys.executable, str(ROOT / "scripts/check_mcp_framework.py")])
    image = identity + ":fixture"
    mounts = ["--mount", "type=volume,source=" + identity + "-data,target=/data",
              "--mount", "type=volume,source=" + identity + "-secrets,target=/run/secrets,readonly"]
    env = ["-e", "MCP_AUTH_SIGNING_KEY_ID=synthetic-fixture-key", "-e", "DJANGO_TRUSTED_PROXY_IPS=127.0.0.1"]
    isolation = ["--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                 "--pids-limit", "64", "--memory", "192m", "--cpus", "0.25", "--tmpfs",
                 "/tmp:rw,noexec,nosuid,size=32m,uid=65532,gid=65532,mode=0700"]
    try:
        with tempfile.TemporaryDirectory(prefix=identity) as directory:
            builder.build(image, Path(directory) / "build.json")
        for suffix in ("-secrets", "-data"):
            run(["docker", "volume", "create", "--label", LABEL + "=" + identity, identity + suffix], capture_output=True)
        run(["docker", "run", "--rm", "--label", LABEL + "=" + identity, "--network", "none", "--read-only", "--user", "0",
             "--mount", "type=volume,source=" + identity + "-secrets,target=/run/secrets",
             "--mount", "type=volume,source=" + identity + "-data,target=/data", "--entrypoint", "/usr/local/bin/python", image, "-c", PREPARE])
        for command in (["migrate", "--noinput"], ["bootstrap_mcp_owner", "--username", "synthetic-owner",
                        "--password-file", "/run/secrets/bootstrap_password", "--subject-output", "/data/synthetic-subject"],
                        ["check", "--deploy", "--fail-level", "ERROR"]):
            run(["docker", "run", "--rm", "--label", LABEL + "=" + identity, *isolation, *mounts, *env,
                 "--entrypoint", "/usr/local/bin/python", image, "/app/manage.py", *command])
        run(["docker", "run", "--rm", "--label", LABEL + "=" + identity, *isolation, *mounts, *env,
             "--entrypoint", "/usr/local/bin/python", image, "-c", VERIFY_STATE])
        run(["docker", "run", "--rm", "--label", LABEL + "=" + identity, *isolation,
             "--mount", "type=bind,source=" + str(ROOT) + ",target=/workspace,readonly",
             "--entrypoint", "/usr/local/bin/python", image, "/workspace/run_source_tests.py"])
        name = identity + "-entrypoint"
        run(["docker", "run", "-d", "--name", name, "--label", LABEL + "=" + identity,
             *isolation, *mounts, *env, image], capture_output=True)
        try:
            run(["docker", "exec", name, "/usr/local/bin/python", "-c", PROBE])
        except subprocess.CalledProcessError:
            # Fixture secrets are synthetic and never printed by application code.
            # Preserve bounded startup diagnostics before exact-run cleanup.
            subprocess.run(["docker", "logs", "--tail", "40", name], check=False, timeout=15)
            raise
        memory = subprocess.check_output(["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", name], text=True).strip()
        print("Synthetic entrypoint idle memory snapshot (not capacity acceptance):", memory)
        run(["docker", "restart", name], capture_output=True)
        run(["docker", "exec", name, "/usr/local/bin/python", "-c", PROBE])
        config = json.loads(subprocess.check_output(["docker", "image", "inspect", image], text=True))[0]["Config"]
        if config["User"] != "65532:65532" or config.get("ExposedPorts") or "--no-proxy-headers" not in config["Entrypoint"]:
            raise ValueError("Unexpected production image privilege/entrypoint")
        fixture_env = dict(os.environ, MCP_AUTH_REPOSITORY="ghcr.io/fixture/auth", MCP_AUTH_SHA256="a" * 64,
                           MCP_AUTH_DATA_DIRECTORY="/synthetic/data", MCP_AUTH_DJANGO_SECRET_FILE="/synthetic/django",
                           MCP_AUTH_SIGNING_KEY_FILE="/synthetic/key", MCP_AUTH_SIGNING_KEY_ID="synthetic-key")
        for active in (False, True):
            model = json.loads(run(["docker", "compose", "-f", str(ROOT / "compose.yml"),
                *( ["--profile", "manual-auth"] if active else []), "config", "--format", "json"],
                env=fixture_env, capture_output=True, text=True).stdout)
            services = model["services"]
            if set(services) != ({"authorization"} if active else set()) or any(value.get("ports") for value in services.values()):
                raise ValueError("Auth profile must remain inactive and have no host ports")
        print("Disposable Linux authorization source/entrypoint/Compose suite passed")
    finally:
        cleanup(identity)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup")
    args = parser.parse_args()
    if args.cleanup:
        cleanup(args.cleanup)
    else:
        main("mcp-auth-test-" + uuid.uuid4().hex)
