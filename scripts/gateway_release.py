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
def maintenance(path=LOCK):
    import fcntl

    private(path.parent)
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600,
                "Unsafe maintenance lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
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
                    (name == "compose.yml" or name in {"scripts/check_host.py", "scripts/gateway_release.py"}
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
    require(set(model["networks"]) == {"notoli_backend", "notoli_frontend", "macromapper"}, "Network policy drift")
    expected = {"notoli_backend": "notoli_backend_private", "notoli_frontend": "notoli_default",
                "macromapper": "macromapper-ingress"}
    require(all({k: v for k, v in model["networks"][key].items() if not (k == "ipam" and v == {})}
                == {"name": name, "external": True}
                for key, name in expected.items()), "Networks must be existing external objects")
    require(proxy["networks"] == {"notoli_backend": {"ipv4_address": "172.30.88.2"},
                                     "notoli_frontend": None, "macromapper": None}, "Proxy trust/address drift")
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


def invariants(allow_missing_proxy=False):
    # Never let a disconnected Actions pipe interrupt host mutation/recovery.
    with redirect_stdout(io.StringIO()):
        check_host.verify("host", allow_missing_proxy=allow_missing_proxy)
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


def health_once(ca=None):
    """Verify edge and loopback origin independently, preserving SNI and TLS checks."""
    for origin in (False, True):
        context = ssl.create_default_context(cafile=ca if origin else None)
        for domain in DOMAINS:
            rules = [("/", 200, "html", None), ("/api/notifications/", 401, "api", None)]
            if domain == DOMAINS[0]:
                rules += [("/.well-known/oauth-authorization-server", 200, "issuer", "https://" + domain),
                          ("/.well-known/oauth-protected-resource/mcp", 200, "resource", "https://" + domain + "/mcp"),
                          ("/mcp", 401, "challenge", None)]
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
                        require("resource_metadata" in response.getheader("WWW-Authenticate", ""), "Missing MCP challenge")
                    else:
                        require(json.loads(body).get(kind) == expected, "Invalid discovery identity")
                finally:
                    connection.close()


def healthy(ca=None):
    # A process deadline also bounds a peer that trickles bytes below socket timeouts.
    import multiprocessing

    context = multiprocessing.get_context("fork")
    for attempt in range(3):
        process = context.Process(target=health_once, args=(ca,))
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
        return record

    def save(self, directory, source, run_url, recovery, model, previous=None):
        record = {"source": source, "directory": str(directory), "image": model["services"]["proxy"]["image"],
                  "configuration": config_identity(model), "actions_run": run_url,
                  "recovery": recovery, "runtime": runtime()}
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
        directory = Path(previous["directory"])
        require(directory.parent == self.root / "releases", "Unsafe recovery reference")
        model = read(directory / "model.json")
        require(config_identity(model) == previous["configuration"], "Recovery checksum mismatch")
        self.syntax(model)
        self.compose(directory, "up", "-d", "--no-deps", "--pull", "never", "--force-recreate", "proxy")
        require(invariants() == journal["invariants"], "Application/network identity changed")
        require(certificate_identity(journal["certs"]) == journal["certificates"], "Certificates changed")
        healthy(ca)
        record = self.save(directory, previous["source"], previous["actions_run"], previous["recovery"], model)
        atomic(self.root / "attempts" / journal["id"] / "result.json",
               {"status": "rolled_back", "promoted_source": journal["source"], "running_source": record["source"]})
        (self.root / "pending.json").unlink(missing_ok=True)
        return record

    def rollback(self, identity, ca):
        require(IDENTITY.fullmatch(identity), "Invalid recovery identity")
        journal = read(self.root / "attempts" / identity / "journal.json")
        pending = self.root / "pending.json"
        interrupted = pending.exists()
        if interrupted:
            require(read(pending)["id"] == identity, "Another interrupted release requires recovery")
        else:
            require(self.current()["recovery"] == identity, "Only the current release may be rolled back")
        # Reboot or an independent app release can change app identities while
        # an interrupted gateway journal remains. Revalidate them under the lock;
        # the gateway itself may be absent or only partially attached.
        current = invariants(allow_missing_proxy=interrupted)
        if interrupted:
            require(current["networks"] == journal["invariants"]["networks"],
                    "Route network IDs changed since interruption")
        journal["invariants"] = current
        atomic(pending, journal)
        return self.restore(journal, ca)

    def deploy(self, archive, identity, run_url, ca):
        require(IDENTITY.fullmatch(identity), "Invalid release identity")
        require(not (self.root / "pending.json").exists(), "Interrupted release requires explicit rollback")
        previous = self.current()
        before = invariants()
        self.capacity()
        certs = next(m["Source"] for m in previous["runtime"]["Mounts"] if m["Destination"] == "/etc/nginx/certs")
        certificates = certificate_identity(certs)
        directory = self.root / "releases" / identity
        directory.mkdir(mode=0o700)
        unpack(archive, directory)
        environment = dict(os.environ, INGRESS_CERTS_DIR=certs)
        # Explicit env and project-directory prevent checkout/.env discovery.
        output = subprocess.run(["docker", "compose", "--env-file", "/dev/null", "-p", "host-ingress", "-f",
                                 str(directory / "compose.yml"), "config", "--format", "json"],
                                env=environment, capture_output=True, text=True, timeout=30)
        require(output.returncode == 0, "Candidate Compose expansion failed")
        model = json.loads(output.stdout)
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
        atomic(attempt / "journal.json", journal)
        durable_tree(attempt)
        # Validate baseline even for a no-op: a broken gateway is never accepted by skipping it.
        healthy(ca)
        if configuration == previous["configuration"]:
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
            require(invariants() == before, "Application/network identity changed")
            require(certificate_identity(certs) == certificates, "Certificates changed")
            healthy(ca)
            self.save(directory, identity[:40], run_url, identity, model, previous)
            atomic(attempt / "result.json", {"status": "success", "running_source": identity[:40]})
            (self.root / "pending.json").unlink()
            return {"status": "success", "running_source": identity[:40]}
        except CommandTimeout:
            # Killing the CLI does not prove the Docker daemon stopped its request.
            # Retain the barrier rather than racing an indeterminate activation.
            raise ReleaseError("Activation timed out; pending barrier retained for explicit recovery") from None
        except Exception:
            self.restore(journal, ca)
            raise ReleaseError("Candidate failed; previous gateway restored; evidence retained") from None


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
            gateway.rollback(args.id, ca)
            result = {"status": "rolled_back", "running_source": read(ROOT / "current.json")["source"]}
        else:
            require(args.id and args.id.startswith(args.source + "-"), "Source/release identity mismatch")
            require(hashlib.sha256(regular(args.archive).read_bytes()).hexdigest() == args.archive_sha256,
                    "Transport checksum mismatch")
            result = gateway.deploy(args.archive, args.id, args.run_url, ca)
        print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (ReleaseError, OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise SystemExit("Gateway operation failed; inspect private host journal; do not retry past a pending barrier") from None
