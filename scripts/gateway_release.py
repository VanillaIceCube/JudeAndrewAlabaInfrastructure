"""Gateway-only Linux release transaction; invoked inside a persistent systemd unit.

All evidence is private. A pending journal blocks new releases until explicit
recovery, even after SIGKILL or host restart. No application or network mutation.
"""

import argparse
from contextlib import contextmanager, redirect_stdout
import copy
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import stat
import subprocess
import tarfile
import time
import uuid

import check_host
import gateway_profile as profiles

ROOT = Path("/opt/host-ingress-deploy")
LOCK = Path("/var/lib/jude-deploy-locks/maintenance.lock")
SHA = re.compile(r"[a-f0-9]{40}")
IDENTITY = re.compile(r"[a-f0-9]{40}-[0-9]+-[0-9]+")
DIGEST = re.compile(r"nginx@sha256:[a-f0-9]{64}")
APPS = ("notoli-backend", "notoli-frontend", "macromapper-backend", "macromapper-frontend")
TARGETS = {"/etc/nginx/nginx.conf": "nginx/nginx.conf",
           "/etc/nginx/conf.d": "nginx/vhosts", "/etc/nginx/snippets": "nginx/snippets"}
DOMAINS = ("notoli.judeandrewalaba.com", "macromapper.judeandrewalaba.com")
DIAGNOSTICS = None
AUTH_RELEASE_ROOT = Path("/opt/mcp-auth-deploy")


class ReleaseError(RuntimeError):
    pass


class CommandTimeout(ReleaseError):
    """A Docker mutation may still be running inside the daemon."""


def require(condition, message):
    if not condition:
        raise ReleaseError(message)


def run(args, timeout=120):
    try:
        result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise CommandTimeout("Command deadline exceeded; inspect private host evidence") from error
    if result.returncode:
        if DIAGNOSTICS is not None and DIAGNOSTICS.is_dir():
            atomic(DIAGNOSTICS / (uuid.uuid4().hex + ".json"),
                   {"command": list(map(str, args)), "exit": result.returncode,
                    "stdout": result.stdout[-8192:], "stderr": result.stderr[-8192:]})
        tool = Path(str(args[0])).name
        phase = str(args[1]) if tool == "docker" and args[1] in {"compose", "pull", "run", "image", "container", "network"} else "command"
        raise ReleaseError(f"Command failed: {tool} {phase} (exit {result.returncode}); inspect private diagnostics")
    return result.stdout


def docker(*args, timeout=120):
    return run(["docker", *args], timeout)


def inspect(kind, name):
    return json.loads(docker(kind, "inspect", name))[0]


def ensure_image(image):
    try:
        inspect("image", image)
    except CommandTimeout:
        raise
    except ReleaseError:
        docker("pull", image, timeout=180)
    require(image in inspect("image", image)["RepoDigests"], "Cached image digest mismatch")


def private(path):
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, "Expected owned private directory")


def regular(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "Expected regular file")
    return path


def atomic(path, value):
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with temporary.open("x", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def read(path):
    return json.loads(regular(path).read_text())


def durable_tree(directory):
    for path in sorted(directory.rglob("*"), reverse=True) + [directory, directory.parent]:
        require(not path.is_symlink(), "Symlinked release evidence")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


@contextmanager
def maintenance(path=LOCK, *, shared=False):
    import fcntl

    private(path.parent)
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600,
                "Unsafe maintenance lock")
        try:
            fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ReleaseError("Maintenance/app release already active") from error
        yield
    finally:
        os.close(fd)


def unpack(archive, destination):
    """No extractall: reject links, devices, traversal and unrelated payloads."""
    with tarfile.open(archive) as source:
        seen = set()
        total = 0
        for item in source:
            name = item.name
            path = Path(name)
            require(not path.is_absolute() and ".." not in path.parts, "Unsafe archive path")
            if item.isdir():
                require(name.rstrip("/") in {"nginx", "nginx/vhosts", "nginx/snippets", "scripts"},
                        "Unexpected payload directory")
                (destination / path).mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            require(item.isfile() and name not in seen and
                    (name in {"compose.yml", profiles.MARKER, profiles.AUTH_MARKER} or name in {"scripts/check_host.py", "scripts/gateway_release.py", "scripts/gateway_profile.py"}
                     or (name.startswith("nginx/") and name.endswith(".conf"))), "Unexpected payload")
            seen.add(name)
            total += item.size
            require(total <= 2 * 1024 * 1024, "Oversized gateway bundle")
            output = destination / path
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with source.extractfile(item) as stream, output.open("xb") as target:
                shutil.copyfileobj(stream, target)
            output.chmod(0o600)
    require({"compose.yml", "nginx/nginx.conf"} <= seen, "Incomplete gateway bundle")


def validate_model(model, certs):
    require(set(model["services"]) == {"proxy"}, "Gateway must contain only proxy")
    proxy = model["services"]["proxy"]
    require(DIGEST.fullmatch(proxy["image"]), "Immutable Nginx digest required")
    require(proxy["container_name"] == "host-ingress-proxy" and proxy["restart"] == "always",
            "Gateway runtime identity drift")
    enabled = "ynab_route" in model["networks"]
    auth_enabled = "mcp_auth_route" in model["networks"]
    require(set(model["networks"]) == {"notoli_backend", "notoli_frontend", "macromapper"} |
            ({"ynab_route"} if enabled else set()) | ({"mcp_auth_route"} if auth_enabled else set()), "Network policy drift")
    expected = {"notoli_backend": "notoli_backend_private", "notoli_frontend": "notoli_default",
                "macromapper": "macromapper-ingress"}
    if enabled:
        expected["ynab_route"] = "ynab_mcp_private"
    if auth_enabled:
        expected["mcp_auth_route"] = "mcp_auth_private"
    require(all({k: v for k, v in model["networks"][key].items() if not (k == "ipam" and v == {})}
                == {"name": name, "external": True}
                for key, name in expected.items()), "Networks must be existing external objects")
    endpoints = {"notoli_backend": {"ipv4_address": "172.30.88.2"}, "notoli_frontend": None,
                 "macromapper": {"ipv4_address": "172.20.0.3"}}
    if enabled:
        endpoints["ynab_route"] = {"ipv4_address": "172.30.89.2"}
    if auth_enabled:
        endpoints["mcp_auth_route"] = {"ipv4_address": "172.30.92.2"}
    require(proxy["networks"] == endpoints, "Proxy trust/address drift")
    require(len(proxy["ports"]) == 2 and
            {(p["target"], str(p["published"]), p.get("host_ip", ""), p["protocol"])
             for p in proxy["ports"]} == {(80, "80", "", "tcp"), (443, "443", "", "tcp")}, "Listener drift")
    volumes = proxy["volumes"]
    require(len(volumes) == 4 and {v["target"] for v in volumes} == set(TARGETS) | {"/etc/nginx/certs"}
            and all(v["type"] == "bind" and v.get("read_only") for v in volumes), "Mount policy drift")
    require(next(v["source"] for v in volumes if v["target"] == "/etc/nginx/certs") == certs,
            "Certificate location must remain unchanged")
    allowed = {"image", "container_name", "restart", "ports", "volumes", "networks", "logging"}
    require({k for k, v in proxy.items() if not (k in {"command", "entrypoint"} and v is None)} <= allowed
            and set(model) <= {"name", "services", "networks"}, "Unsupported Compose setting")
    require(proxy["logging"] == {"driver": "json-file", "options": {"max-file": "3", "max-size": "10m"}},
            "Logging policy drift")


def config_identity(model):
    normalized = copy.deepcopy(model)
    files = {}
    for volume in normalized["services"]["proxy"]["volumes"]:
        if volume["target"] not in TARGETS:
            continue
        path = Path(volume["source"])
        require(path.is_file() or path.is_dir(), "Missing configuration mount source")
        entries = [path] if path.is_file() else sorted(path.rglob("*"))
        require(not path.is_symlink(), "Symlinked configuration")
        for entry in entries:
            require(not entry.is_symlink(), "Symlinked configuration")
            if entry.is_file():
                key = volume["target"] + ("/" + str(entry.relative_to(path)) if entry != path else "")
                files[key] = hashlib.sha256(regular(entry).read_bytes()).hexdigest()
        volume["source"] = volume["target"]
    return hashlib.sha256(json.dumps([normalized, files], sort_keys=True).encode()).hexdigest()


def runtime():
    value = inspect("container", "host-ingress-proxy")
    require(value["State"]["Running"], "Gateway is stopped")
    value["Mounts"] = sorted(value["Mounts"], key=lambda mount: mount["Destination"])
    return {key: value[key] for key in ("Id", "Image", "Config", "HostConfig", "Mounts")}


def invariants(allow_missing_proxy=False, *, ynab_enabled=False, auth_enabled=False):
    # Never let a disconnected Actions pipe interrupt host mutation/recovery.
    with redirect_stdout(io.StringIO()):
        options = {"allow_stopped_gateway": True} if ynab_enabled or auth_enabled else {}
        if auth_enabled:
            options["auth_enabled"] = True
        check_host.verify("host", allow_missing_proxy=allow_missing_proxy, ynab_enabled=ynab_enabled, **options)
    apps = {}
    for name in APPS:
        value = inspect("container", name)
        require(value["State"]["Running"], "Companion application is not running")
        value["Mounts"] = sorted(value["Mounts"], key=lambda mount: mount["Destination"])
        apps[name] = {key: value[key] for key in ("Id", "Image", "Config", "HostConfig", "Mounts")}
        apps[name]["StartedAt"] = value["State"]["StartedAt"]
    return {
        "apps": apps,
        "networks": {name: inspect("network", name)["Id"] for name in check_host.NETWORKS},
    }


def certificate_identity(certs):
    result = {}
    for name in ("origin.pem", "origin.key"):
        path = regular(Path(certs) / name)
        info = path.stat()
        result[name] = [info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode),
                        hashlib.sha256(path.read_bytes()).hexdigest()]
    return result


def notoli_auth_mode():
    environment = inspect("container", "notoli-backend")["Config"].get("Env") or []
    modes = [value.split("=", 1)[1] for value in environment if value.startswith("DJANGO_MCP_AUTH_MODE=")]
    require(len(modes) <= 1 and all(mode in {"legacy", "central"} for mode in modes), "Invalid Notoli MCP authentication mode")
    return modes[0] if modes else "legacy"


def macro_mcp_enabled():
    environment = inspect("container", "macromapper-backend")["Config"].get("Env") or []
    values = [value.split("=", 1)[1] for value in environment if value.startswith("DJANGO_MCP_ENABLED=")]
    require(len(values) <= 1 and all(value in {"0", "1"} for value in values), "Invalid MacroMapper MCP registry setting")
    return values == ["1"]


def macro_route_contract(model):
    attachment = model["services"]["proxy"].get("networks", {}).get("macromapper")
    require(attachment is None or attachment == {"ipv4_address": "172.20.0.3"}, "Invalid accepted MacroMapper proxy attachment")
    return attachment is not None


def health_once(ca=None, macro_routes=True):
    """Verify edge and loopback origin independently, preserving SNI and TLS checks."""
    central = notoli_auth_mode() == "central"
    macro_enabled = macro_mcp_enabled()
    require(macro_routes or not macro_enabled, "Legacy gateway cannot provide enabled MacroMapper MCP readiness")
    for origin in (False, True):
        context = ssl.create_default_context(cafile=ca if origin else None)
        for domain in DOMAINS:
            rules = [("/", 200, "html", None), ("/api/notifications/", 401, "api", None)]
            if domain == DOMAINS[0]:
                rules += [("/.well-known/oauth-authorization-server", 410 if central else 200,
                           "retired-issuer" if central else "issuer", "https://" + domain),
                          ("/.well-known/oauth-protected-resource/mcp", 200, "resource", "https://" + domain + "/mcp"),
                          ("/mcp", 401, "challenge", None)]
            elif macro_routes:
                rules += [("/.well-known/oauth-authorization-server", 404, "disabled-mcp", None),
                          ("/.well-known/oauth-protected-resource/mcp", 200 if macro_enabled else 404,
                           "resource" if macro_enabled else "disabled-mcp", "https://" + domain + "/mcp"),
                          ("/mcp", 401 if macro_enabled else 404, "challenge" if macro_enabled else "disabled-mcp", None)]
            for path, status, kind, expected in rules:
                connection = http.client.HTTPSConnection(domain, timeout=5, context=context)
                if origin:
                    # HTTPSConnection wraps this socket using the original domain as SNI.
                    import socket
                    connection._create_connection = lambda address, timeout, source_address: socket.create_connection(
                        ("127.0.0.1", 443), timeout, source_address)
                try:
                    connection.request("GET", path, headers={"User-Agent": "JudeGatewayRelease/1.0",
                                       "Cache-Control": "no-cache, no-store"})
                    response = connection.getresponse()
                    body = response.read(256 * 1024)
                    require(response.status == status, "Unexpected readiness status")
                    if kind == "html":
                        require(b"<html" in body.lower(), "Missing frontend HTML")
                    elif kind == "api":
                        require("application/json" in response.getheader("Content-Type", "")
                                and isinstance(json.loads(body), dict) and "detail" in json.loads(body), "Invalid API response")
                    elif kind == "challenge":
                        challenge = response.getheader("WWW-Authenticate", "")
                        require("resource_metadata" in challenge, "Missing MCP challenge")
                        if domain == DOMAINS[1]:
                            scheme, _, parameters = challenge.partition(" ")
                            metadata = [field.strip() for field in parameters.split(",")
                                        if field.strip().startswith("resource_metadata")]
                            require(scheme.lower() == "bearer" and metadata == [
                                'resource_metadata="https://' + domain + '/.well-known/oauth-protected-resource/mcp"'],
                                "Invalid MacroMapper resource challenge")
                    elif kind in {"retired-issuer", "disabled-mcp"}:
                        require("no-store" in response.getheader("Cache-Control", ""), "MCP route must be uncached")
                    else:
                        discovery = json.loads(body)
                        require(discovery.get(kind) == expected, "Invalid discovery identity")
                        if kind == "resource" and (central or domain == DOMAINS[1]):
                            require(discovery.get("authorization_servers") == ["https://auth.judeandrewalaba.com"],
                                    "Notoli resource advertises an unexpected central issuer")
                finally:
                    connection.close()


def bounded_health(probe, *arguments):
    # A process deadline also bounds a peer that trickles bytes below socket timeouts.
    import multiprocessing

    context = multiprocessing.get_context("fork")
    for attempt in range(3):
        process = context.Process(target=probe, args=arguments)
        process.start()
        process.join(80)
        if process.is_alive():
            process.kill()
            process.join()
        if process.exitcode == 0:
            return
        if attempt == 2:
            raise ReleaseError("Gateway readiness exhausted its bounded retry budget")
        time.sleep(2)


def healthy(ca=None, *, macro_routes=True):
    bounded_health(health_once, ca, macro_routes)


def ynab_health_once(profile, strict, ca):
    domain = "ynab.judeandrewalaba.com"
    for origin in ((True, False) if strict and profile == "enabled" else (True,)):
        context = ssl.create_default_context(cafile=ca if origin else None)
        paths = ["/mcp", "/.well-known/oauth-protected-resource/mcp"] if profile == "disabled" or strict else ["/mcp"]
        for path in paths:
            connection = http.client.HTTPSConnection(domain, timeout=5, context=context)
            if origin:
                import socket
                connection._create_connection = lambda address, timeout, source_address: socket.create_connection(
                    ("127.0.0.1", 443), timeout, source_address)
            try:
                post = profile == "enabled" and path == "/mcp"
                connection.request("POST" if post else "GET", path, body=b"{}" if post else None,
                    headers={"Content-Type": "application/json", "Accept": "application/json",
                             "User-Agent": "JudeGatewayRelease/1.0", "Cache-Control": "no-cache, no-store"})
                response = connection.getresponse()
                body = response.read(16 * 1024)
                require("no-store" in response.getheader("Cache-Control", ""), "Missing private route cache policy")
                if profile == "disabled":
                    require(response.status == 410, "Missing YNAB tombstone")
                elif path == "/mcp":
                    require(response.status in ({401} if strict else {401, 502, 503}), "Unexpected YNAB route status")
                    if response.status == 401:
                        require('resource_metadata="https://' + domain + '/.well-known/oauth-protected-resource/mcp"'
                                in response.getheader("WWW-Authenticate", ""), "Invalid YNAB challenge")
                else:
                    require(response.status == 200 and json.loads(body).get("resource") == "https://" + domain + "/mcp",
                            "Invalid YNAB resource metadata")
            finally:
                connection.close()


def route_health(profile, strict=False, ca=None):
    if profile != "base":
        bounded_health(ynab_health_once, profile, strict, ca)


def ynab_reexposure_allowed():
    """Restored issuer state cannot revive still-live offline YNAB access JWTs."""
    if AUTH_RELEASE_ROOT.exists() or AUTH_RELEASE_ROOT.is_symlink():
        private(AUTH_RELEASE_ROOT)
    pending = AUTH_RELEASE_ROOT / "pending.json"
    require(not pending.exists() and not pending.is_symlink(), "Authorization recovery blocks YNAB exposure")
    quarantine = AUTH_RELEASE_ROOT / "ynab-jwt-quarantine.json"
    if quarantine.exists() or quarantine.is_symlink():
        info = regular(quarantine).stat()
        require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= 256,
                "Unsafe authorization recovery quarantine")
        record = read(quarantine)
        require(isinstance(record, dict) and set(record) == {"version", "not_before"} and
                type(record["version"]) is int and record["version"] == 1 and
                type(record["not_before"]) is int and record["not_before"] > 0,
                "Malformed authorization recovery quarantine")
        require(time.time() >= record["not_before"], "YNAB JWT recovery quarantine has not expired")


def ynab_exposure_transition(previous, candidate):
    if candidate == "enabled" and previous != "enabled":
        ynab_reexposure_allowed()


AUTH_DOMAIN = "auth.judeandrewalaba.com"
AUTH_PATHS = ("/.well-known/oauth-authorization-server", "/o/authorize/", "/o/token/", "/o/revoke_token/",
              "/o/introspect/", "/o/authorized_tokens/", "/o/authorized_tokens/1/delete/", "/accounts/login/", "/accounts/logout/",
              "/accounts/password_change/", "/accounts/password_change/done/")


def auth_health_once(profile, strict, ca):
    for origin in ((True, False) if strict and profile == "enabled" else (True,)):
        paths = AUTH_PATHS if profile == "disabled" else ("/.well-known/oauth-authorization-server",)
        for path in paths:
            connection = http.client.HTTPSConnection(AUTH_DOMAIN, timeout=5,
                context=ssl.create_default_context(cafile=ca if origin else None))
            if origin:
                import socket
                connection._create_connection = lambda address, timeout, source_address: socket.create_connection(
                    ("127.0.0.1", 443), timeout, source_address)
            try:
                connection.request("GET", path, headers={"User-Agent": "JudeGatewayRelease/1.0",
                    "Accept": "application/json", "Cache-Control": "no-cache, no-store"})
                response = connection.getresponse()
                body = response.read(16 * 1024 + 1)
                require(len(body) <= 16 * 1024 and "no-store" in response.getheader("Cache-Control", ""),
                        "Invalid authorization route cache/body policy")
                if profile == "disabled":
                    require(response.status == 410, "Missing authorization tombstone")
                elif response.status not in {502, 503} or strict:
                    require(response.status == 200, "Unexpected authorization metadata status")
                    metadata = json.loads(body)
                    issuer = "https://" + AUTH_DOMAIN
                    require(metadata.get("issuer") == issuer and
                            metadata.get("authorization_endpoint") == issuer + "/o/authorize/" and
                            metadata.get("token_endpoint") == issuer + "/o/token/" and
                            "S256" in metadata.get("code_challenge_methods_supported", []),
                            "Invalid authorization server metadata")
            finally:
                connection.close()


def auth_route_health(profile, strict=False, ca=None):
    if profile != "base":
        bounded_health(auth_health_once, profile, strict, ca)


def ynab_identity():
    route = check_host.ynab_route(allow_missing_proxy=True, allow_stopped_gateway=True)
    apps = {}
    for name in ("ynab-mcp-gateway-1", "ynab-mcp-egress-1"):
        ids = docker("ps", "-aq", "--filter", "name=^/" + name + "$").split()
        require(len(ids) <= 1, "Ambiguous YNAB app identity")
        if ids:
            value = inspect("container", ids[0])
            apps[name] = [value["Id"], value["Image"], value["State"]["StartedAt"]]
    return {"network": route["Id"], "apps": apps}


def auth_identity():
    route = check_host.auth_route(allow_missing_proxy=True, allow_stopped_gateway=True)
    ids = docker("ps", "-aq", "--filter", "name=^/mcp-auth-server$").split()
    require(len(ids) == 1, "Missing or ambiguous authorization app identity")
    value = inspect("container", ids[0])
    private(AUTH_RELEASE_ROOT)
    pending = AUTH_RELEASE_ROOT / "pending.json"
    require(not pending.exists() and not pending.is_symlink(), "Pending authorization release blocks route exposure")
    accepted = read(AUTH_RELEASE_ROOT / "current.json")
    require(not accepted.get("disabled") and SHA.fullmatch(accepted.get("source", "")), "Missing accepted authorization release")
    value["Mounts"] = sorted(value["Mounts"], key=lambda mount: mount["Destination"])
    require(all(value[key] == accepted["runtime"][key] for key in ("Id", "Image", "Config", "HostConfig", "Mounts")) and
            value["State"]["StartedAt"] == accepted["runtime"]["started"], "Authorization differs from accepted runtime identity")
    return {"network": route["Id"], "app": [value["Id"], value["Image"], value["State"]["StartedAt"]],
            "source": accepted["source"]}


def profile_invariants(profile, allow_missing_proxy=False, *, auth_profile="base"):
    options = {}
    if profile == "enabled":
        options["ynab_enabled"] = True
    if auth_profile == "enabled":
        options["auth_enabled"] = True
    return invariants(allow_missing_proxy=allow_missing_proxy, **options)


class Gateway:
    def __init__(self, root=ROOT):
        global DIAGNOSTICS
        self.root = root
        private(root)
        for name in ("releases", "attempts", "incoming"):
            private(root / name)
        DIAGNOSTICS = root / "diagnostics"
        DIAGNOSTICS.mkdir(mode=0o700, exist_ok=True)
        private(DIAGNOSTICS)

    def compose(self, directory, *args):
        return docker("compose", "-p", "host-ingress", "-f", directory / "model.json", *args)

    def profile(self, record):
        profile = profiles.model_profile(read(Path(record["directory"]) / "model.json"))
        require(record.get("profile", profile) == profile, "Accepted route profile drift")
        return profile

    def auth_profile(self, record):
        profile = profiles.model_profile(read(Path(record["directory"]) / "model.json"), auth=True)
        require(record.get("auth_profile", "base") == profile, "Accepted authorization profile drift")
        return profile

    def current(self):
        record = read(self.root / "current.json")
        directory = Path(record["directory"])
        require(directory.parent == self.root / "releases", "Invalid accepted release directory")
        private(directory)
        require(runtime() == record["runtime"], "Live gateway differs from accepted runtime")
        live = copy.deepcopy(read(directory / "model.json"))
        mounts = {m["Destination"]: m["Source"] for m in record["runtime"]["Mounts"]}
        for volume in live["services"]["proxy"]["volumes"]:
            volume["source"] = mounts[volume["target"]]
        require(config_identity(live) == record["configuration"], "Live configuration drift")
        require(config_identity(read(directory / "model.json")) == record["configuration"], "Recovery configuration drift")
        macro_route_contract(live)  # Accept the historical DHCP model without rewriting it.
        self.profile(record)
        self.auth_profile(record)
        return record

    def save(self, directory, source, run_url, recovery, model, previous=None):
        record = {"source": source, "directory": str(directory), "image": model["services"]["proxy"]["image"],
                  "configuration": config_identity(model), "actions_run": run_url,
                  "recovery": recovery, "runtime": runtime()}
        record["profile"] = profiles.model_profile(model)
        record["auth_profile"] = profiles.model_profile(model, auth=True)
        if previous:
            record["previous_source"] = previous["source"]
        atomic(self.root / "current.json", record)
        return record

    def snapshot(self, model, directory):
        model = copy.deepcopy(model)
        for volume in model["services"]["proxy"]["volumes"]:
            if volume["target"] not in TARGETS:
                continue
            original = Path(volume["source"])
            target = directory / TARGETS[volume["target"]]
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            require(not original.is_symlink(), "Symlinked config source")
            if original.is_dir():
                # Identity validation rejects nested symlinks before copying.
                shutil.copytree(original, target)
            else:
                shutil.copyfile(regular(original), target)
            volume["source"] = str(target)
        for path in directory.rglob("*"):
            path.chmod(0o700 if path.is_dir() else 0o600)
        atomic(directory / "model.json", model)
        durable_tree(directory)
        return model

    def syntax(self, model):
        args = ["run", "--rm", "--network", "none"]
        for volume in model["services"]["proxy"]["volumes"]:
            args += ["--mount", "type=bind,src=" + volume["source"] + ",dst=" + volume["target"] + ",readonly"]
        docker(*args, model["services"]["proxy"]["image"], "nginx", "-t", timeout=30)

    def capacity(self):
        disk = shutil.disk_usage(self.root)
        memory = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        require(disk.free >= max(disk.total // 5, 1024 ** 3)
                and int(memory["MemAvailable"].split()[0]) >= 512 * 1024, "Insufficient release/recovery capacity")

    def adopt(self, directory, source, ca):
        require(not (self.root / "current.json").exists() and not (self.root / "pending.json").exists(),
                "Gateway baseline already initialized or interrupted")
        require(run(["git", "-C", directory, "rev-parse", "HEAD"]).strip() == source, "Baseline source mismatch")
        require(not run(["git", "-C", directory, "status", "--porcelain", "--untracked-files=all", "--",
                         "compose.yml", "nginx"]).strip(), "Baseline gateway checkout is not clean")
        model = json.loads(docker("compose", "-p", "host-ingress", "-f", directory / "compose.yml", "config", "--format", "json"))
        live = runtime()
        certs = next(m["Source"] for m in live["Mounts"] if m["Destination"] == "/etc/nginx/certs")
        validate_model(model, certs)
        expected_mounts = {(v["target"], v["source"], False) for v in model["services"]["proxy"]["volumes"]}
        require({(m["Destination"], m["Source"], m["RW"]) for m in live["Mounts"]} == expected_mounts,
                "Baseline mounts do not match live gateway")
        require(inspect("image", model["services"]["proxy"]["image"])["Id"] == live["Image"], "Baseline image mismatch")
        logging = model["services"]["proxy"]["logging"]
        require(live["HostConfig"]["RestartPolicy"]["Name"] == "always"
                and live["HostConfig"]["LogConfig"] == {"Type": logging["driver"], "Config": logging["options"]},
                "Baseline runtime policy drift")
        require(set(live["HostConfig"]["PortBindings"]) == {"80/tcp", "443/tcp"}
                and all(bindings and all(binding["HostPort"] == port.split("/")[0]
                                         and binding["HostIp"] in {"", "0.0.0.0", "::"} for binding in bindings)
                        for port, bindings in live["HostConfig"]["PortBindings"].items()), "Baseline port drift")
        config_identity(model)
        invariants()
        healthy(ca)
        target = self.root / "releases" / (source + "-0-0")
        target.mkdir(mode=0o700)
        captured = self.snapshot(model, target)
        self.save(target, source, "operator-adoption", None, captured)

    def restore(self, journal, ca):
        previous = journal["previous"]
        protected = (self.profile(previous) == "base" and journal.get("profile") == "disabled" or
                     self.auth_profile(previous) == "base" and journal.get("auth_profile", "base") == "disabled")
        if protected:
            # First tombstone activation has no protected predecessor. Recover
            # its already syntax-tested disabled candidate, retaining the host
            # protection through both ordinary failure and interrupted recovery.
            staged = self.root / "releases" / journal["id"]
            require(profiles.read(staged) == journal["profile"] and
                    profiles.read(staged, auth=True) == journal.get("auth_profile", "base"), "Protected recovery profile mismatch")
            require(config_identity(read(staged / "model.json")) == journal["configuration"], "Protected recovery checksum mismatch")
            previous = {"directory": str(staged), "source": journal["source"], "actions_run": journal["actions_run"],
                        "recovery": None, "configuration": journal["configuration"], "profile": journal["profile"],
                        "auth_profile": journal.get("auth_profile", "base")}
        directory = Path(previous["directory"])
        require(directory.parent == self.root / "releases", "Unsafe recovery reference")
        model = read(directory / "model.json")
        require(config_identity(model) == previous["configuration"], "Recovery checksum mismatch")
        profile = self.profile(previous)
        auth_profile = self.auth_profile(previous)
        ynab_exposure_transition(journal.get("profile", "base"), profile)
        macro_routes = macro_route_contract(model)
        require(macro_routes or not macro_mcp_enabled(), "Enabled MacroMapper MCP blocks legacy gateway restoration")
        if auth_profile == "enabled":
            require(auth_identity() == journal.get("auth_state"), "Authorization identity changed before recovery exposure")
        self.syntax(model)
        self.compose(directory, "up", "-d", "--no-deps", "--pull", "never", "--force-recreate", "proxy")
        require(profile_invariants(profile, auth_profile=auth_profile) == journal["invariants"], "Application/network identity changed")
        if journal.get("ynab_state") is not None:
            require(ynab_identity() == journal["ynab_state"], "YNAB app/network identity changed")
        if journal.get("auth_state") is not None:
            require(auth_identity() == journal["auth_state"], "Authorization app/network identity changed")
        require(certificate_identity(journal["certs"]) == journal["certificates"], "Certificates changed")
        healthy(ca, macro_routes=macro_routes)
        route_health(profile, strict=profile == "enabled" and journal.get("profile") == "disabled", ca=ca)
        auth_route_health(auth_profile, strict=auth_profile == "enabled" and journal.get("auth_profile") == "disabled", ca=ca)
        record = self.save(directory, previous["source"], previous["actions_run"], previous["recovery"], model)
        atomic(self.root / "attempts" / journal["id"] / "result.json",
               {"status": "protected" if protected else "rolled_back", "promoted_source": journal["source"], "running_source": record["source"]})
        (self.root / "pending.json").unlink(missing_ok=True)
        return dict(record, outcome="protected" if protected else "rolled_back")

    def rollback(self, identity, ca):
        require(IDENTITY.fullmatch(identity), "Invalid recovery identity")
        journal = read(self.root / "attempts" / identity / "journal.json")
        pending = self.root / "pending.json"
        interrupted = pending.exists()
        if interrupted:
            require(read(pending)["id"] == identity, "Another interrupted release requires recovery")
        else:
            current_record = self.current()
            require(current_record["recovery"] == identity, "Only the current release may be rolled back")
            profiles.transition_pair(self.profile(current_record), self.profile(journal["previous"]),
                                     self.auth_profile(current_record), self.auth_profile(journal["previous"]))
        # Reboot or an independent app release can change app identities while
        # an interrupted gateway journal remains. Revalidate them under the lock;
        # the gateway itself may be absent or only partially attached.
        protected = journal.get("ynab_state") is not None
        auth_protected = journal.get("auth_state") is not None
        active_profile = ("enabled" if protected else "base") if interrupted else self.profile(current_record)
        active_auth = ("enabled" if auth_protected else "base") if interrupted else self.auth_profile(current_record)
        current = profile_invariants(active_profile, allow_missing_proxy=interrupted, auth_profile=active_auth)
        if interrupted:
            require(current["networks"] == journal["invariants"]["networks"],
                    "Route network IDs changed since interruption")
        if protected:
            ynab = ynab_identity()
            require(ynab["network"] == journal["ynab_state"]["network"], "YNAB route network was replaced")
            journal["ynab_state"] = ynab
        if auth_protected:
            auth = auth_identity()
            require(auth["network"] == journal["auth_state"]["network"], "Authorization route network was replaced")
            journal["auth_state"] = auth
        journal["invariants"] = current
        atomic(pending, journal)
        return self.restore(journal, ca)

    def deploy(self, archive, identity, run_url, ca):
        require(IDENTITY.fullmatch(identity), "Invalid release identity")
        require(not (self.root / "pending.json").exists(), "Interrupted release requires explicit rollback")
        previous = self.current()
        previous_profile = self.profile(previous)
        previous_auth_profile = self.auth_profile(previous)
        before = profile_invariants(previous_profile, auth_profile=previous_auth_profile)
        self.capacity()
        certs = next(m["Source"] for m in previous["runtime"]["Mounts"] if m["Destination"] == "/etc/nginx/certs")
        certificates = certificate_identity(certs)
        directory = self.root / "releases" / identity
        directory.mkdir(mode=0o700)
        unpack(archive, directory)
        profile = profiles.read(directory)
        auth_profile = profiles.read(directory, auth=True)
        profiles.transition_pair(previous_profile, profile, previous_auth_profile, auth_profile)
        ynab_exposure_transition(previous_profile, profile)
        environment = dict(os.environ, INGRESS_CERTS_DIR=certs)
        # Explicit env and project-directory prevent checkout/.env discovery.
        output = subprocess.run(["docker", "compose", "--env-file", "/dev/null", "-p", "host-ingress", "-f",
                                 str(directory / "compose.yml"), "config", "--format", "json"],
                                env=environment, capture_output=True, text=True, timeout=30)
        require(output.returncode == 0, "Candidate Compose expansion failed")
        model = json.loads(output.stdout)
        profiles.apply(model, profile)
        profiles.apply(model, auth_profile, auth=True)
        validate_model(model, certs)
        require(all(volume["source"] == str(directory / TARGETS[volume["target"]])
                    for volume in model["services"]["proxy"]["volumes"] if volume["target"] in TARGETS),
                "Candidate configuration must be staged inside its release directory")
        atomic(directory / "model.json", model)
        durable_tree(directory)
        configuration = config_identity(model)
        attempt = self.root / "attempts" / identity
        attempt.mkdir(mode=0o700)
        journal = {"id": identity, "source": identity[:40], "previous": previous,
                   "invariants": before, "certs": certs, "certificates": certificates,
                   "actions_run": run_url, "configuration": configuration,
                   "image": model["services"]["proxy"]["image"]}
        journal["profile"] = profile
        journal["auth_profile"] = auth_profile
        journal["ynab_state"] = ynab_identity() if "enabled" in {previous_profile, profile} else None
        journal["auth_state"] = auth_identity() if "enabled" in {previous_auth_profile, auth_profile} else None
        atomic(attempt / "journal.json", journal)
        durable_tree(attempt)
        # Validate baseline even for a no-op: a broken gateway is never accepted by skipping it.
        previous_model = read(Path(previous["directory"]) / "model.json")
        healthy(ca, macro_routes=macro_route_contract(previous_model))
        if configuration == previous["configuration"]:
            route_health(profile, ca=ca)
            auth_route_health(auth_profile, ca=ca)
            atomic(attempt / "result.json", {"status": "unchanged", "promoted_source": identity[:40],
                                            "running_source": previous["source"]})
            return {"status": "unchanged", "running_source": previous["source"]}
        self.capacity()
        ensure_image(model["services"]["proxy"]["image"])
        self.capacity()
        self.syntax(model)
        self.compose(directory, "config", "--quiet")
        atomic(self.root / "pending.json", journal)
        try:
            self.compose(directory, "up", "-d", "--no-deps", "--pull", "never", "--force-recreate", "proxy")
            require(runtime()["Image"] == inspect("image", model["services"]["proxy"]["image"])["Id"], "Image mismatch")
            require(profile_invariants(profile, auth_profile=auth_profile) == before, "Application/network identity changed")
            if journal["ynab_state"] is not None:
                require(ynab_identity() == journal["ynab_state"], "YNAB app/network identity changed")
            if journal["auth_state"] is not None:
                require(auth_identity() == journal["auth_state"], "Authorization app/network identity changed")
            require(certificate_identity(certs) == certificates, "Certificates changed")
            healthy(ca)
            route_health(profile, strict=profile == "enabled" and previous_profile != "enabled", ca=ca)
            auth_route_health(auth_profile, strict=auth_profile == "enabled" and previous_auth_profile != "enabled", ca=ca)
            self.save(directory, identity[:40], run_url, identity, model, previous)
            atomic(attempt / "result.json", {"status": "success", "running_source": identity[:40]})
            (self.root / "pending.json").unlink()
            return {"status": "success", "running_source": identity[:40]}
        except CommandTimeout:
            # Killing the CLI does not prove the Docker daemon stopped its request.
            # Retain the barrier rather than racing an indeterminate activation.
            raise ReleaseError("Activation timed out; pending barrier retained for explicit recovery") from None
        except Exception:
            restored = self.restore(journal, ca)
            outcome = "protected tombstone restored" if restored.get("outcome") == "protected" else "previous gateway restored"
            raise ReleaseError("Candidate failed; " + outcome + "; evidence retained") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("adopt", "deploy", "rollback"))
    parser.add_argument("--source", required=True)
    parser.add_argument("--id")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--archive-sha256")
    parser.add_argument("--directory", type=Path, default=Path("/opt/host-ingress"))
    parser.add_argument("--run-url", default="operator")
    args = parser.parse_args()
    require(SHA.fullmatch(args.source), "Full source SHA required")
    os.umask(0o077)
    # Operator-owned trust anchor; never supplied by a candidate release.
    ca = str(ROOT / "origin-ca.pem") if (ROOT / "origin-ca.pem").exists() else None
    with maintenance():
        gateway = Gateway()
        if args.operation == "adopt":
            gateway.adopt(args.directory, args.source, ca)
            result = {"status": "adopted", "running_source": args.source}
        elif args.operation == "rollback":
            recovered = gateway.rollback(args.id, ca)
            result = {"status": recovered.get("outcome", "rolled_back"), "running_source": read(ROOT / "current.json")["source"]}
        else:
            require(args.id and args.id.startswith(args.source + "-"), "Source/release identity mismatch")
            require(hashlib.sha256(regular(args.archive).read_bytes()).hexdigest() == args.archive_sha256,
                    "Transport checksum mismatch")
            result = gateway.deploy(args.archive, args.id, args.run_url, ca)
        result["profile"] = gateway.profile(read(ROOT / "current.json"))
        result["auth_profile"] = gateway.auth_profile(read(ROOT / "current.json"))
        print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (ReleaseError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise SystemExit("Gateway operation failed; inspect private host journal; do not retry past a pending barrier") from None
