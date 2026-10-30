"""Real app-only Docker switching/recovery, including SIGKILL after mutation.

Uses synthetic HTTP/socket images, unique projects and three internal networks.
Only artifact scanning, source/secret staging and companion inventory are fixture
providers; the journal, ownership checks, locks and Compose mutations are real.
The actual gateway/protocol/secret policy is tested by its existing image runner.
"""
import hashlib
import ipaddress
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ynab_release as release

IMAGE = "python@sha256:623674a14ef93d052bb9b0de4dbf5f28eb578a35263838941cc8aa43213c1487"
LABEL = "infrastructure.ynab.release.fixture"
SERVER = """from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(b'fixture-ready')
HTTPServer(('0.0.0.0',8000),Handler).serve_forever()
"""
SOCKET = "import socket;s=socket.socket();s.bind(('0.0.0.0',3128));s.listen();\nwhile True: c,_=s.accept();c.close()"


@unittest.skipUnless(os.name != "nt" and os.geteuid() == 0 and shutil.which("docker"),
                     "Linux root-owned disposable journal and Docker transaction fixture")
class AppDockerReleaseTests(unittest.TestCase):
    def test_upgrade_failed_upgrade_rollback_and_sigkill_preserve_companions(self):
        prefix = "ynab-release-test-" + uuid.uuid4().hex[:10]
        docker = release.common.docker
        names = {role: prefix + "-" + role + "-1" for role in ("gateway", "egress")}
        networks = {}
        label = LABEL + "=" + prefix
        with tempfile.TemporaryDirectory(prefix=prefix, dir=os.environ.get("YNAB_RELEASE_FIXTURE_ROOT")) as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            for directory in ("releases", "records", "attempts", "locks"):
                (root / directory).mkdir(mode=0o700)
            (root / "data").mkdir(mode=0o700)
            os.chown(root / "data", 65532, 65532)
            journal = root / "data" / ".ynab-mcp-undo.json"
            journal.write_text('[{"fixture":"initial"}]')
            journal.chmod(0o600)
            os.chown(journal, 65532, 65532)
            for filename in ("maintenance.lock", "ynab-mcp.lock"):
                (root / "locks" / filename).touch(mode=0o600)
            with sqlite3.connect(root / "db.sqlite3") as database:
                database.execute("CREATE TABLE fixture (value TEXT)")
                database.execute("INSERT INTO fixture VALUES ('unchanged')")
            (root / "origin.pem").write_bytes(b"synthetic-companion-certificate-unchanged")
            (root / "origin.key").write_bytes(b"synthetic-companion-key-unchanged")
            try:
                docker("image", "inspect", IMAGE)
                docker("run", "-d", "--name", prefix + "-companion", "--label", label, "--network", "none",
                       "--read-only", "--cap-drop", "ALL", IMAGE, "python", "-c", "import time;time.sleep(300)")
                def companions():
                    container = release.common.inspect("container", prefix + "-companion")
                    return {"id": container["Id"], "started": container["State"]["StartedAt"],
                            "files": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                      for name in ("db.sqlite3", "origin.pem", "origin.key")}}
                baseline = companions()
                model_networks = {}
                octet = int(uuid.uuid4().hex[:2], 16)
                for index, key in enumerate(("route", "egress_private", "egress_public")):
                    name = prefix + "-" + key
                    subnet = f"10.249.{octet}.{index * 16}/28"
                    docker("network", "create", "--internal", "--subnet", subnet, "--gateway",
                           str(ipaddress.ip_network(subnet).network_address + 1), "--label", label, name)
                    network = release.common.inspect("network", name)
                    subnet = network["IPAM"]["Config"][0]["Subnet"]
                    base = ipaddress.ip_network(subnet).network_address
                    model_networks[key] = {"external": True, "name": name}
                    allowed = ({names["gateway"]: str(base + 3)} if key == "route" else
                               {names["egress"]: str(base + 2)} if key == "egress_public" else
                               {names["gateway"]: str(base + 3), names["egress"]: str(base + 2)})
                    networks[name] = (True, subnet, allowed)
                def address(key, role):
                    return networks[model_networks[key]["name"]][2][names[role]]
                def stage(app, source, images, secrets):
                    directory = root / "releases" / (source + "-" + uuid.uuid4().hex)
                    directory.mkdir(mode=0o700)
                    handler = directory / "handler.py"
                    handler.write_text(SERVER + "# source " + source + "\n")
                    handler.chmod(0o444)
                    common = {"profiles": ["manual-gateway"], "image": IMAGE, "user": "0:0",
                        "read_only": True, "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
                        "pids_limit": 32, "mem_limit": 128 * 1024 * 1024, "restart": "no", "labels": {LABEL: prefix},
                        "logging": {"driver": "none"}}
                    gateway = dict(common, container_name=names["gateway"], entrypoint=["/usr/local/bin/python"],
                        command=["-c", "raise SystemExit(3)"] if source == "c" * 40 else ["-B", "/fixture/handler.py"],
                        environment={"YNAB_ALLOW_WRITES": "1", "YNAB_DISABLE_AGENT_CONFIG_FALLBACK": "1"},
                        volumes=[{"type": "bind", "source": str(handler), "target": "/fixture/handler.py", "read_only": True},
                                 {"type": "bind", "source": str(root / "data"), "target": "/data", "read_only": False,
                                  "bind": {"create_host_path": False}}],
                        networks={key: {"ipv4_address": address(key, "gateway")} for key in ("route", "egress_private")})
                    egress = dict(common, container_name=names["egress"], entrypoint=["/usr/local/bin/python"],
                        command=["-c", SOCKET], volumes=[],
                        networks={key: {"ipv4_address": address(key, "egress")} for key in ("egress_private", "egress_public")})
                    egress["networks"]["egress_private"]["aliases"] = ["ynab-egress"]
                    gateway["networks"]["route"]["aliases"] = ["ynab-mcp-gateway"]
                    release.common.atomic(directory / "model.json", {"name": prefix, "services": {
                        "gateway": gateway, "egress": egress}, "networks": model_networks})
                    release.common.durable_tree(directory)
                    return {"id": directory.name, "source": source, "directory": str(directory), "images": images,
                            "files": release.files_identity(directory), "journal": app.journal_identity()}
                with patch.object(release, "PROJECT", prefix), patch.object(release, "NAMES", names), \
                     patch.object(release, "NETWORKS", networks), patch.object(release, "companions", side_effect=companions), \
                     patch.object(release, "preflight", return_value={"fixture": "only"}) as scanner, \
                     patch.object(release.Release, "stage", autospec=True, side_effect=stage):
                    app = release.Release(root, Path("fixture-scanner"), Path("fixture-cache"))
                    images = {role: IMAGE for role in names}
                    network_ids = release.topology()
                    with release.locks(root / "locks"):
                        app.deploy("a" * 40, images, {}, initial=True)
                        first = release.common.read(root / "current.json")
                        app.deploy("b" * 40, images, {})
                        # Financial state is external: image rollback must retain
                        # new operation evidence instead of rewinding its journal.
                        docker("exec", "--user", "65532:65532", names["gateway"], "python", "-c",
                               "from pathlib import Path;Path('/data/.ynab-mcp-undo.json').write_text('[{\"fixture\":\"new-operation\"}]')")
                        app.rollback(outcome_confirmed=True)
                    restored = release.common.read(root / "current.json")
                    self.assertEqual(restored["files"], first["files"])
                    self.assertEqual(restored["images"], first["images"])
                    self.assertEqual(companions(), baseline)
                    self.assertEqual(journal.read_text(), '[{"fixture":"new-operation"}]')
                    with release.locks(root / "locks"):
                        with self.assertRaises(release.common.ReleaseError):
                            app.deploy("c" * 40, images, {})
                        self.assertTrue((root / "pending.json").exists())
                        # Docker update preserves Compose's config hash. Recovery
                        # must recreate the old model, not reuse this drift.
                        docker("update", "--memory", "256m", names["egress"])
                        app.recover(outcome_confirmed=True)
                        self.assertEqual(release.common.inspect("container", names["egress"])["HostConfig"]["Memory"], 128 * 1024 * 1024)
                    # Kill the controller after Compose completed but before its
                    # readiness/acceptance phase; no mutation is retried by CI.
                    child = os.fork()
                    if child == 0:
                        try:
                            with release.locks(root / "locks"), patch.object(release.Release, "ready", side_effect=lambda: os.kill(os.getpid(), signal.SIGKILL)):
                                app.deploy("d" * 40, images, {})
                        finally:
                            os._exit(2)
                    _, status = os.waitpid(child, 0)
                    self.assertTrue(os.WIFSIGNALED(status))
                    self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)
                    reopened = release.Release(root, Path("fixture-scanner"), Path("fixture-cache"))
                    with release.locks(root / "locks"):
                        with self.assertRaises(release.common.ReleaseError):
                            reopened.deploy("b" * 40, images, {})
                        reopened.recover(outcome_confirmed=True)
                    accepted = release.common.read(root / "current.json")
                    self.assertEqual(accepted["source"], "a" * 40)
                    self.assertEqual(accepted["files"], first["files"])
                    self.assertEqual(release.topology(require_app=True), network_ids)
                    self.assertEqual(companions(), baseline)
                    self.assertFalse((root / "pending.json").exists())
                    self.assertEqual(journal.read_text(), '[{"fixture":"new-operation"}]')
                    self.assertEqual(accepted["journal"], first["journal"])
                    # The forked child's mock calls live in its private memory.
                    self.assertEqual(scanner.call_count, 6)
            finally:
                for kind in ("container", "network"):
                    ids = docker(kind, "ls", "-aq" if kind == "container" else "-q", "--filter", "label=" + label).split()
                    if ids:
                        docker(kind, "rm", *(["-f", "-v"] if kind == "container" else []), *ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
