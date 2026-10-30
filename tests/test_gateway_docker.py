"""Real disposable gateway releases, rejection, reversal and repeat acceptance.

Only production names/subnet/listener policy and external service health are
substituted. The transaction, Docker commands, config hashing and journal are real.
"""

import copy
from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gateway_release as release

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "Run Docker transaction fixtures in Linux/CI")
class GatewayDockerTests(unittest.TestCase):
    def test_real_release_rejection_rollback_repeat_and_companion_preservation(self):
        prefix = "gateway-test-" + uuid.uuid4().hex[:10]
        docker = release.docker
        names, networks = [], []
        with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            for name in ("incoming", "attempts", "releases"):
                (root / name).mkdir(mode=0o700)
            certs = root / "certs"
            certs.mkdir(mode=0o700)
            release.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                         "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
                         "-keyout", certs / "origin.key", "-out", certs / "origin.pem"])
            fixture = root / "fixture"
            fixture.mkdir()
            shutil.copyfile(ROOT / "compose.yml", fixture / "compose.yml")
            (fixture / "nginx/vhosts").mkdir(parents=True)
            (fixture / "nginx/snippets").mkdir()
            nginx = "events {}\nhttp { include /etc/nginx/conf.d/*.conf; }\n"
            (fixture / "nginx/nginx.conf").write_text(nginx)
            good = ('server { listen 443 ssl; ssl_certificate /etc/nginx/certs/origin.pem; '
                    'ssl_certificate_key /etc/nginx/certs/origin.key; location / { return 200 "accepted"; } }\n')
            health_path = fixture / "nginx/vhosts/health.conf"
            health_path.write_text(good)
            env = dict(os.environ, INGRESS_CERTS_DIR=str(certs))
            config = json.loads(subprocess.run(["docker", "compose", "-p", prefix, "-f", str(fixture / "compose.yml"),
                                               "config", "--format", "json"], env=env, check=True,
                                              capture_output=True, text=True).stdout)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            proxy = config["services"]["proxy"]
            proxy["container_name"] = prefix + "-proxy"
            proxy["ports"] = [{"target": 443, "published": str(port), "host_ip": "127.0.0.1", "protocol": "tcp", "mode": "ingress"}]
            # Dynamic addresses on unique disposable networks avoid all production objects.
            proxy["networks"]["notoli_backend"] = None
            proxy["networks"]["macromapper"] = None
            for key in config["networks"]:
                config["networks"][key] = {"external": True, "name": prefix + "-" + key}
            for volume in proxy["volumes"]:
                if volume["target"] in release.TARGETS:
                    volume["source"] = "./" + release.TARGETS[volume["target"]]
            (fixture / "compose.yml").write_text(json.dumps(config))
            config = json.loads(docker("compose", "--env-file", "/dev/null", "-p", "host-ingress", "-f",
                                       fixture / "compose.yml", "config", "--format", "json"))

            class FixtureGateway(release.Gateway):
                def compose(self, directory, *args):
                    return docker("compose", "-p", prefix, "-f", directory / "model.json", *args)

            gateway = FixtureGateway(root)
            original_validate = release.validate_model

            def validate(model, cert_directory):
                normalized = copy.deepcopy(model)
                service = normalized["services"]["proxy"]
                service["container_name"] = "host-ingress-proxy"
                service["ports"] = [{"target": p, "published": str(p), "protocol": "tcp"} for p in (80, 443)]
                service["networks"]["notoli_backend"] = {"ipv4_address": "172.30.88.2"}
                service["networks"]["macromapper"] = {"ipv4_address": "172.20.0.3"}
                for key, name in (("notoli_backend", "notoli_backend_private"), ("notoli_frontend", "notoli_default"),
                                  ("macromapper", "macromapper-ingress")):
                    normalized["networks"][key] = {"name": name, "external": True}
                original_validate(normalized, cert_directory)

            def runtime():
                value = release.inspect("container", prefix + "-proxy")
                release.require(value["State"]["Running"], "Fixture proxy stopped")
                value["Mounts"] = sorted(value["Mounts"], key=lambda mount: mount["Destination"])
                return {key: value[key] for key in ("Id", "Image", "Config", "HostConfig", "Mounts")}

            def invariants(allow_missing_proxy=False):
                return {"apps": {name: [release.inspect("container", name)["Id"],
                                       release.inspect("container", name)["State"]["StartedAt"]]
                                 for name in names if name != prefix + "-proxy"},
                        "networks": {name: release.inspect("network", name)["Id"] for name in networks},
                        "data": hashlib.sha256((root / "db.sqlite3").read_bytes()).hexdigest()}

            def healthy(ca=None, *, macro_routes=True):
                for attempt in range(20):
                    connection = http.client.HTTPSConnection("localhost", port, timeout=2,
                                                           context=ssl.create_default_context(cafile=str(certs / "origin.pem")))
                    try:
                        connection.request("GET", "/", headers={"User-Agent": "JudeGatewayRelease/1.0"})
                        response = connection.getresponse()
                        release.require(response.status == 200 and response.read() == b"accepted", "Unhealthy fixture")
                        return
                    except (OSError, http.client.HTTPException):
                        if attempt == 19:
                            raise
                        time.sleep(0.1)
                    finally:
                        connection.close()

            def bundle(revision, marker=None, invalid=False):
                if marker:
                    health_path.write_text(good.replace("accepted", marker))
                else:
                    health_path.write_text(good)
                (fixture / "nginx/nginx.conf").write_text(nginx + ("invalid_directive;\n" if invalid else "# " + revision + "\n"))
                target = root / (revision + ".tar")
                with tarfile.open(target, "w") as archive:
                    archive.add(fixture / "compose.yml", arcname="compose.yml")
                    archive.add(fixture / "nginx", arcname="nginx")
                return target

            @contextmanager
            def expect_restored():
                try:
                    yield
                except release.ReleaseError as error:
                    # These commands concern only this test's synthetic resources.
                    # Production diagnostics remain private and are never published.
                    diagnostics = [release.read(path) for path in (root / "diagnostics").glob("*.json")]
                    self.assertIn("previous gateway restored", str(error),
                                  "Disposable fixture diagnostics: " + json.dumps(diagnostics))
                else:
                    self.fail("Expected rejected candidate and verified restoration")

            try:
                for network in config["networks"].values():
                    docker("network", "create", network["name"])
                    networks.append(network["name"])
                (root / "db.sqlite3").write_bytes(b"untouched companion data")
                for app in release.APPS:
                    name = prefix + "-" + app
                    docker("run", "-d", "--name", name, "--network", networks[0],
                           "--mount", "type=bind,src=" + str(root / "db.sqlite3") + ",dst=/db.sqlite3,readonly",
                           "python:3.12-alpine", "sleep", "600")
                    names.append(name)
                baseline = root / "releases" / ("a" * 40 + "-0-0")
                baseline.mkdir(mode=0o700)
                initial = copy.deepcopy(config)
                for volume in initial["services"]["proxy"]["volumes"]:
                    if volume["target"] in release.TARGETS:
                        volume["source"] = str(fixture / release.TARGETS[volume["target"]])
                initial = gateway.snapshot(initial, baseline)
                gateway.compose(baseline, "up", "-d", "--no-deps", "proxy")
                names.append(prefix + "-proxy")
                with patch.object(release, "runtime", runtime), patch.object(release, "invariants", invariants), \
                        patch.object(release, "macro_mcp_enabled", return_value=False), \
                        patch.object(release, "shared_consumers_active", return_value=False), \
                        patch.object(release, "validate_model", validate), patch.object(release, "healthy", healthy):
                    healthy()
                    gateway.save(baseline, "a" * 40, "fixture-baseline", None, initial)
                    before = invariants()
                    cert_before = release.certificate_identity(str(certs))
                    live_before = runtime()["Id"]
                    # Identical effective payload: no restart even though promoted source differs.
                    target = root / "same.tar"
                    with tarfile.open(target, "w") as archive:
                        archive.add(fixture / "compose.yml", arcname="compose.yml")
                        archive.add(fixture / "nginx", arcname="nginx")
                    unchanged = gateway.deploy(target, "b" * 40 + "-1-1", "run/1", None)
                    self.assertEqual(unchanged["status"], "unchanged")
                    self.assertEqual(runtime()["Id"], live_before)
                    with self.assertRaises(release.ReleaseError):
                        gateway.deploy(bundle("c", invalid=True), "c" * 40 + "-2-1", "run/2", None)
                    self.assertEqual(runtime()["Id"], live_before)
                    with expect_restored():
                        gateway.deploy(bundle("d", marker="unhealthy"), "d" * 40 + "-3-1", "run/3", None)
                    self.assertEqual(release.read(root / "current.json")["source"], "a" * 40)
                    self.assertFalse((root / "pending.json").exists())
                    for revision, run_id in (("e", 4), ("f", 5)):
                        result = gateway.deploy(bundle(revision), revision * 40 + f"-{run_id}-1", f"run/{run_id}", None)
                        self.assertEqual(result["running_source"], revision * 40)
                    gateway.rollback("f" * 40 + "-5-1", None)
                    self.assertEqual(release.read(root / "current.json")["source"], "e" * 40)
                    original_compose = gateway.compose
                    failed_directory = root / "releases" / ("9" * 40 + "-6-1")
                    def activate_then_fail(directory, *args):
                        result = original_compose(directory, *args)
                        if directory == failed_directory and args[0] == "up":
                            raise release.ReleaseError("Injected activation failure after container recreation")
                        return result
                    with patch.object(gateway, "compose", side_effect=activate_then_fail), expect_restored():
                        gateway.deploy(bundle("9"), failed_directory.name, "run/6", None)
                    self.assertEqual(release.read(root / "current.json")["source"], "e" * 40)
                    healthy()
                    self.assertEqual(invariants(), before)
                    self.assertEqual(release.certificate_identity(str(certs)), cert_before)
                    interrupted_directory = root / "releases" / ("8" * 40 + "-7-1")
                    def interrupt_after_activation(directory, *args):
                        result = original_compose(directory, *args)
                        if directory == interrupted_directory and args[0] == "up":
                            raise KeyboardInterrupt()
                        return result
                    with patch.object(gateway, "compose", side_effect=interrupt_after_activation), \
                            self.assertRaises(KeyboardInterrupt):
                        gateway.deploy(bundle("8"), interrupted_directory.name, "run/7", None)
                    # Reproduce reboot/restart identities and a missing gateway.
                    for name in names:
                        if name != prefix + "-proxy":
                            docker("restart", "--time", "1", name)
                    docker("rm", "-f", prefix + "-proxy")
                    rebooted = invariants(allow_missing_proxy=True)
                    self.assertNotEqual(rebooted["apps"], before["apps"])
                    gateway.rollback(interrupted_directory.name, None)
                    self.assertEqual(invariants(), rebooted)
                    self.assertFalse((root / "pending.json").exists())
                    self.assertEqual(release.read(root / "current.json")["source"], "e" * 40)
                    healthy()
            finally:
                for name in reversed(names):
                    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
                for network in reversed(networks):
                    subprocess.run(["docker", "network", "rm", network], capture_output=True)


if __name__ == "__main__":
    unittest.main()
