"""Validate and launch the shared Nginx proxy on its existing networks."""

import argparse
from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import stat
import subprocess
import sys
import tarfile
import time

import check_host

ROOT = Path("/opt/host-ingress-deploy")
LOCK = Path("/var/lib/jude-deploy-locks/maintenance.lock")
SHA = re.compile(r"[a-f0-9]{40}")
IDENTITY = re.compile(r"[a-f0-9]{40}-[0-9]+-[0-9]+")
DIGEST = re.compile(r"nginx@sha256:[a-f0-9]{64}")
TARGETS = {
    "/etc/nginx/nginx.conf": "nginx/nginx.conf",
    "/etc/nginx/conf.d": "nginx/vhosts",
    "/etc/nginx/snippets": "nginx/snippets",
}
DOMAINS = ("notoli.judeandrewalaba.com", "macromapper.judeandrewalaba.com")


class ReleaseError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ReleaseError(message)


def run(args, timeout=120, env=None):
    try:
        result = subprocess.run(
            list(map(str, args)),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as error:
        raise ReleaseError("Command deadline exceeded") from error
    if result.returncode:
        tool = Path(str(args[0])).name
        phase = (
            str(args[1])
            if tool == "docker"
            and args[1] in {"compose", "pull", "run", "image", "container", "network"}
            else "command"
        )
        raise ReleaseError(f"Command failed: {tool} {phase} (exit {result.returncode})")
    return result.stdout


def docker(*args, timeout=120):
    return run(["docker", *args], timeout)


def inspect(kind, name):
    return json.loads(docker(kind, "inspect", name))[0]


def ensure_image(image):
    try:
        inspect("image", image)
    except ReleaseError:
        docker("pull", image, timeout=180)
    require(
        image in inspect("image", image)["RepoDigests"], "Cached image digest mismatch"
    )


def require_private_directory(path):
    info = path.lstat()
    require(
        stat.S_ISDIR(info.st_mode)
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == 0o700,
        "Expected owned private directory",
    )


def require_regular_file(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "Expected regular file")
    return path


@contextmanager
def maintenance(path=LOCK):
    import fcntl

    require_private_directory(path.parent)
    fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(
            stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1
            and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o600,
            "Unsafe maintenance lock",
        )
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
            require(
                not path.is_absolute() and ".." not in path.parts, "Unsafe archive path"
            )
            if item.isdir():
                require(
                    name.rstrip("/") in {"nginx", "nginx/vhosts", "nginx/snippets"},
                    "Unexpected payload directory",
                )
                (destination / path).mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            require(
                item.isfile()
                and name not in seen
                and (
                    name == "compose.yml"
                    or name in {"nginx/check_host.py", "nginx/gateway_release.py"}
                    or (name.startswith("nginx/") and name.endswith(".conf"))
                ),
                "Unexpected payload",
            )
            seen.add(name)
            total += item.size
            require(total <= 2 * 1024 * 1024, "Oversized gateway bundle")
            output = destination / path
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with source.extractfile(item) as stream, output.open("xb") as target:
                shutil.copyfileobj(stream, target)
            output.chmod(0o600)
    require({"compose.yml", "nginx/nginx.conf"} <= seen, "Incomplete gateway bundle")


def validate_gateway_compose(model, directory, certificate_directory):
    services = model["services"]
    require(set(services) == {"proxy"}, "Gateway must contain only proxy")
    proxy = services["proxy"]
    require(DIGEST.fullmatch(proxy["image"]), "Immutable Nginx digest required")
    require(
        proxy["container_name"] == "host-ingress-proxy"
        and proxy["restart"] == "always",
        "Gateway runtime identity drift",
    )

    networks = model["networks"]
    expected_network_names = {
        "notoli_backend": "notoli_backend_private",
        "notoli_frontend": "notoli_default",
        "macromapper": "macromapper-ingress",
    }
    require(set(networks) == set(expected_network_names), "Network policy drift")
    for network_key, expected_name in expected_network_names.items():
        network = networks[network_key].copy()
        # Compose may include an empty IPAM object for an external network.
        if network.get("ipam") == {}:
            del network["ipam"]
        require(
            network == {"name": expected_name, "external": True},
            "Networks must be existing external objects",
        )

    expected_proxy_networks = {
        "notoli_backend": {"ipv4_address": "172.30.88.2"},
        "notoli_frontend": None,
        "macromapper": {"ipv4_address": "172.20.0.3"},
    }
    require(proxy["networks"] == expected_proxy_networks, "Proxy trust/address drift")

    ports = proxy["ports"]
    require(len(ports) == 2, "Listener drift")
    listeners = {
        (
            port["target"],
            str(port["published"]),
            port.get("host_ip", ""),
            port["protocol"],
        )
        for port in ports
    }
    expected_listeners = {(80, "80", "", "tcp"), (443, "443", "", "tcp")}
    require(listeners == expected_listeners, "Listener drift")

    volumes = proxy["volumes"]
    require(len(volumes) == 4, "Mount policy drift")
    certificate_target = "/etc/nginx/certs"
    expected_mount_targets = set(TARGETS) | {certificate_target}
    mount_targets = {volume["target"] for volume in volumes}
    require(mount_targets == expected_mount_targets, "Mount policy drift")
    for volume in volumes:
        require(
            volume["type"] == "bind" and volume.get("read_only"), "Mount policy drift"
        )
    certificate_source = next(
        volume["source"] for volume in volumes if volume["target"] == certificate_target
    )
    require(
        certificate_source == certificate_directory,
        "Certificate location must remain unchanged",
    )

    for volume in volumes:
        if volume["target"] in TARGETS:
            require(
                Path(volume["source"]) == directory / TARGETS[volume["target"]],
                "Configuration mount outside staged source",
            )
    vhosts = {p.name for p in (directory / "nginx/vhosts").glob("*.conf")}
    require(
        vhosts == {"00-notoli.conf", "10-macromapper.conf"}, "Unexpected gateway vhost"
    )

    allowed_proxy_fields = {
        "image",
        "container_name",
        "restart",
        "ports",
        "volumes",
        "networks",
        "logging",
    }
    proxy_fields = {
        field
        for field, value in proxy.items()
        if field not in {"command", "entrypoint"} or value is not None
    }
    require(proxy_fields <= allowed_proxy_fields, "Unsupported Compose setting")
    require(
        set(model) <= {"name", "services", "networks"}, "Unsupported Compose setting"
    )

    expected_logging = {
        "driver": "json-file",
        "options": {"max-file": "3", "max-size": "10m"},
    }
    require(proxy["logging"] == expected_logging, "Logging policy drift")


def certificate_identity(certs):
    result = {}
    for name in ("origin.pem", "origin.key"):
        path = require_regular_file(Path(certs) / name)
        info = path.stat()
        result[name] = [
            info.st_uid,
            info.st_gid,
            stat.S_IMODE(info.st_mode),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        ]
    return result


def health_once(domains, ca):
    """Verify edge and loopback origin independently, preserving SNI and TLS checks."""
    for origin in (False, True):
        context = ssl.create_default_context(cafile=ca if origin else None)
        for domain in domains:
            rules = [
                ("/", 200, "html", None),
                ("/api/notifications/", 401, "api", None),
            ]
            if domain == DOMAINS[0]:
                rules += [
                    (
                        "/.well-known/oauth-authorization-server",
                        200,
                        "issuer",
                        "https://" + domain,
                    ),
                    (
                        "/.well-known/oauth-protected-resource/mcp",
                        200,
                        "resource",
                        "https://" + domain + "/mcp",
                    ),
                    ("/mcp", 401, "challenge", None),
                ]
            for path, status, kind, expected in rules:
                connection = http.client.HTTPSConnection(
                    domain, timeout=5, context=context
                )
                if origin:
                    # HTTPSConnection wraps this socket using the original domain as SNI.
                    import socket

                    connection._create_connection = (
                        lambda address, timeout, source_address: (
                            socket.create_connection(
                                ("127.0.0.1", 443), timeout, source_address
                            )
                        )
                    )
                try:
                    connection.request(
                        "GET",
                        path,
                        headers={
                            "User-Agent": "JudeGatewayRelease/1.0",
                            "Cache-Control": "no-cache, no-store",
                        },
                    )
                    response = connection.getresponse()
                    body = response.read(256 * 1024)
                    require(response.status == status, "Unexpected readiness status")
                    if kind == "html":
                        require(b"<html" in body.lower(), "Missing frontend HTML")
                    elif kind == "api":
                        require(
                            "application/json" in response.getheader("Content-Type", "")
                            and isinstance(json.loads(body), dict)
                            and "detail" in json.loads(body),
                            "Invalid API response",
                        )
                    elif kind == "challenge":
                        require(
                            "resource_metadata"
                            in response.getheader("WWW-Authenticate", ""),
                            "Missing MCP challenge",
                        )
                    else:
                        require(
                            json.loads(body).get(kind) == expected,
                            "Invalid discovery identity",
                        )
                finally:
                    connection.close()


def healthy(domains, ca):
    # A process deadline also bounds a peer that trickles bytes below socket timeouts.
    import multiprocessing

    context = multiprocessing.get_context("fork")
    for attempt in range(3):
        process = context.Process(target=health_once, args=(domains, ca))
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


def check_syntax(model):
    proxy = model["services"]["proxy"]
    args = ["run", "--rm", "--network", "none"]
    for mount in proxy["volumes"]:
        args += [
            "--mount",
            f"type=bind,src={mount['source']},dst={mount['target']},readonly",
        ]
    docker(*args, proxy["image"], "nginx", "-t", timeout=30)


def deploy(archive, checksum, identity):
    require(IDENTITY.fullmatch(identity), "Invalid deployment identity")
    require_private_directory(ROOT)
    incoming = ROOT / "incoming"
    require_private_directory(incoming)
    attempt = incoming / identity
    require_private_directory(attempt)
    require(archive == attempt / "source.tar", "Unexpected upload path")
    require(
        hashlib.sha256(require_regular_file(archive).read_bytes()).hexdigest()
        == checksum,
        "Transport checksum mismatch",
    )
    directory = attempt / "config"
    directory.mkdir(mode=0o700)
    unpack(archive, directory)
    check_host.verify(allow_missing_proxy=True, allow_missing_apps=True)

    # Reuse the operator's live certificate mount, including a custom location.
    # On first launch the Compose file supplies the host default.
    env = os.environ.copy()
    existing = docker("ps", "-aq", "--filter", "name=^/host-ingress-proxy$").strip()
    if existing:
        runtime = inspect("container", existing)
        require(
            (runtime["Config"]["Labels"] or {}).get("com.docker.compose.project")
            == "host-ingress",
            "Gateway name is already in use",
        )
        mounts = [
            m
            for m in runtime["Mounts"]
            if m["Destination"] == "/etc/nginx/certs" and not m["RW"]
        ]
        require(len(mounts) == 1, "Expected one read-only operator certificate mount")
        env["INGRESS_CERTS_DIR"] = mounts[0]["Source"]
    compose = [
        "docker",
        "compose",
        "--env-file",
        "/dev/null",
        "-p",
        "host-ingress",
        "-f",
        directory / "compose.yml",
    ]
    model = json.loads(run([*compose, "config", "--format", "json"], env=env))
    certs = env.get("INGRESS_CERTS_DIR") or "/root/apps/notoli/certs"
    validate_gateway_compose(model, directory, certs)
    certificates = certificate_identity(certs)
    image = model["services"]["proxy"]["image"]
    ensure_image(image)
    check_syntax(model)
    run([*compose, "up", "-d", "--no-deps", "--pull", "never", "proxy"], env=env)
    require(
        inspect("container", "host-ingress-proxy")["Image"]
        == inspect("image", image)["Id"],
        "Gateway image mismatch",
    )
    require(certificate_identity(certs) == certificates, "Certificates changed")
    members = check_host.verify(allow_missing_apps=True)
    domains = [
        domain
        for domain in DOMAINS
        if all(
            domain.split(".")[0] + "-" + service in members
            for service in ("backend", "frontend")
        )
    ]
    if domains:
        ca = ROOT / "origin-ca.pem"
        healthy(domains, str(ca) if ca.exists() else None)


def main():
    if sys.argv[1:2] == ["check-config"]:
        parser = argparse.ArgumentParser(
            description="Check the staged gateway configuration."
        )
        parser.add_argument("--directory", type=Path, required=True)
        parser.add_argument("--certificates", required=True)
        parser.add_argument("--syntax", action="store_true")
        args = parser.parse_args(sys.argv[2:])
        model = json.load(sys.stdin)
        validate_gateway_compose(model, args.directory.resolve(), args.certificates)
        if args.syntax:
            ensure_image(model["services"]["proxy"]["image"])
            check_syntax(model)
        return

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    with maintenance():
        deploy(args.archive, args.archive_sha256, args.id)
    print("Gateway launched " + args.id)


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
        raise SystemExit("Gateway launch failed: " + detail) from None
