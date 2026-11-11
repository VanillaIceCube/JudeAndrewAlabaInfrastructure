"""Read-only legacy tombstones and a synthetic forward/rollback transaction."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import gateway_release as release


@unittest.skipIf(os.name == "nt", "Linux private release contract")
class RetirementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.root.chmod(0o700)
        for name in ("releases", "attempts", "incoming"):
            (self.root / name).mkdir(mode=0o700)
        self.old = self.root / "releases" / ("a" * 40 + "-1-1")
        self.old.mkdir(mode=0o700)
        self.write_base(self.old)
        self.old_model = self.model(self.old)
        for field, marker, filename, digest in release.RETIRED_ROUTES:
            (self.old / "nginx/vhosts" / filename).write_bytes(
                (ROOT / "tests/fixtures/retired-gateway" / filename).read_bytes())
            release.atomic(self.old / marker, {"version": 1, "profile": "disabled", "vhost_sha256": digest})
        release.atomic(self.old / "model.json", self.old_model)
        self.live = self.runtime(self.old_model, "old")
        self.enterContext(patch.object(release, "runtime", side_effect=lambda: copy.deepcopy(self.live)))
        self.gateway = release.Gateway(self.root)
        self.previous = self.gateway.save(self.old, "a" * 40, "synthetic-disabled", None, self.old_model)
        self.identity = "b" * 40 + "-2-1"
        self.archive = self.root / "base.tar"
        with tarfile.open(self.archive, "w") as archive:
            for name, value in self.base_files().items():
                item = tarfile.TarInfo(name)
                item.size = len(value)
                archive.addfile(item, io.BytesIO(value))

    @staticmethod
    def base_files():
        return {"compose.yml": b"{}", "nginx/nginx.conf": b"events {}\nhttp {}\n",
                "nginx/vhosts/10-app.conf": b"# synthetic existing application\n",
                "nginx/snippets/tls.conf": b"# synthetic TLS fixture\n"}

    def write_base(self, directory):
        for name, data in self.base_files().items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes(data)

    def model(self, directory):
        return {"name": "host-ingress", "networks": {
            key: {"name": name, "external": True} for key, name in
            (("notoli_backend", "notoli_backend_private"), ("notoli_frontend", "notoli_default"),
             ("macromapper", "macromapper-ingress"))}, "services": {"proxy": {
            "image": "nginx@sha256:" + "c" * 64, "container_name": "host-ingress-proxy", "restart": "always",
            "ports": [{"target": port, "published": str(port), "protocol": "tcp"} for port in (80, 443)],
            "networks": {"notoli_backend": {"ipv4_address": "172.30.88.2"}, "notoli_frontend": None,
                         "macromapper": {"ipv4_address": "172.20.0.3"}},
            "volumes": [{"type": "bind", "source": str(directory / name), "target": target, "read_only": True}
                        for target, name in release.TARGETS.items()] +
                       [{"type": "bind", "source": "/synthetic-certs", "target": "/etc/nginx/certs", "read_only": True}],
            "logging": {"driver": "json-file", "options": {"max-file": "3", "max-size": "10m"}}}}}

    @staticmethod
    def runtime(model, identity):
        return {"Id": identity, "Image": "synthetic-image", "Mounts": [
            {"Destination": value["target"], "Source": value["source"], "RW": False}
            for value in model["services"]["proxy"]["volumes"]]}

    def test_disabled_generation_forward_deploys_base_and_rolls_back_exact_tombstones(self):
        self.assertEqual(self.gateway.current(), self.previous)
        def expand(command, **kwargs):
            directory = Path(command[command.index("-f") + 1]).parent
            return subprocess.CompletedProcess(command, 0, json.dumps(self.model(directory)))
        def compose(directory, *args):
            if args[0] == "up":
                self.live = self.runtime(release.read(directory / "model.json"), directory.name)
        with (patch.object(self.gateway, "capacity"), patch.object(self.gateway, "syntax"),
              patch.object(self.gateway, "compose", side_effect=compose) as commands,
              patch.object(release.subprocess, "run", side_effect=expand),
              patch.object(release, "invariants", return_value={"apps": "same", "networks": "same"}),
              patch.object(release, "certificate_identity", return_value="same"),
              patch.object(release, "healthy") as health, patch.object(release, "ensure_image"),
              patch.object(release, "inspect", return_value={"Id": "synthetic-image"})):
            result = self.gateway.deploy(self.archive, self.identity, "synthetic-base", None)
            self.assertEqual(result["status"], "success")
            current = self.gateway.current()
            self.assertEqual((current["profile"], current["auth_profile"]), ("base", "base"))
            self.assertFalse((Path(current["directory"]) / "nginx/vhosts/zz-ynab.conf").exists())
            self.gateway.rollback(self.identity, None)
            restored = self.gateway.current()
            self.assertEqual(restored["configuration"], self.previous["configuration"])
            self.assertEqual((restored["profile"], restored["auth_profile"]), ("disabled", "disabled"))
            self.assertEqual([call.args[0] for call in commands.call_args_list if call.args[1] == "up"],
                             [self.root / "releases" / self.identity, self.old])
            self.assertGreaterEqual(health.call_count, 3)
        self.assertFalse((self.root / "pending.json").exists())

    def test_enabled_record_or_network_cannot_bypass_containment(self):
        for field in ("profile", "auth_profile"):
            record = self.previous | {field: "enabled"}
            release.atomic(self.root / "current.json", record)
            with self.subTest(field=field), self.assertRaises(release.ReleaseError):
                self.gateway.current()
            with patch.object(self.gateway, "compose") as commands, self.assertRaises(release.ReleaseError):
                self.gateway.restore({"previous": record}, None)
            commands.assert_not_called()
        model = copy.deepcopy(self.old_model)
        model["networks"]["retired_route"] = {"external": True, "name": "retired_private"}
        with self.assertRaisesRegex(release.ReleaseError, "detached"):
            release.retired_route_state(self.old, model, self.previous)

    def test_marker_and_disabled_vhost_must_match_exact_reviewed_bytes(self):
        field, marker_name, filename, digest = release.RETIRED_ROUTES[0]
        marker = self.old / marker_name
        original = release.read(marker)
        for changed in (original | {"profile": "enabled"}, original | {"version": True},
                        original | {"vhost_sha256": "0" * 64}, original | {"extra": True}):
            release.atomic(marker, changed)
            with self.subTest(changed=changed), self.assertRaises(release.ReleaseError):
                release.retired_route_state(self.old, self.old_model, self.previous)
        release.atomic(marker, original)
        (self.old / "nginx/vhosts" / filename).write_text("# modified tombstone\n")
        with self.assertRaises(release.ReleaseError):
            release.retired_route_state(self.old, self.old_model, self.previous)


if __name__ == "__main__":
    unittest.main(verbosity=2)
