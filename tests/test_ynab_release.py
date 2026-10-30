"""Durable app-only release barriers and exact matched configuration recovery."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ynab_release as release

SOURCE = "a" * 40
SECOND = "b" * 40


class AppContractTests(unittest.TestCase):
    def test_network_gateway_and_accepted_route_attachment_are_enforced(self):
        def network(name):
            internal, subnet, _ = release.NETWORKS[name]
            return {"Driver": "bridge", "Internal": internal, "EnableIPv6": False,
                    "IPAM": {"Config": [{"Subnet": subnet, "Gateway": subnet.split("/")[0][:-1] + "1"}]},
                    "Containers": {}, "Id": name}
        with patch.object(release.common, "inspect", side_effect=lambda kind, name: network(name)):
            self.assertEqual(len(release.topology()), 3)
        invalid = network("ynab_mcp_private")
        invalid["IPAM"]["Config"][0]["Gateway"] = "172.30.89.4"
        with patch.object(release.common, "inspect", return_value=invalid), self.assertRaises(release.common.ReleaseError):
            release.topology()
        proxy = {"NetworkSettings": {"Networks": {}}}
        accepted = {"directory": str(release.common.ROOT / "releases" / "fixture"), "profile": "enabled", "runtime": {}}
        with patch.object(release.common, "inspect", return_value=proxy), \
             patch.object(release.common, "read", side_effect=[accepted, {}]), \
             patch.object(release.common, "private"), patch.object(release.common, "runtime", return_value={}), \
             patch.object(release.common.profiles, "model_profile", return_value="enabled"), \
             self.assertRaisesRegex(release.common.ReleaseError, "route attachment"):
            release.companions()

    def test_missing_alias_and_relaxed_capability_or_seccomp_cannot_be_accepted(self):
        app = release.Release.__new__(release.Release)
        expected = {"volumes": [], "networks": {"route": {"ipv4_address": "172.30.89.3", "aliases": ["ynab-mcp-gateway"]}},
                    "mem_limit": 128, "pids_limit": 32, "restart": "no", "user": "65532:65532"}
        model = {"services": {"gateway": expected}, "networks": {"route": {"name": "ynab_mcp_private"}}}
        live = {"HostConfig": {"ReadonlyRootfs": True, "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
                               "Memory": 128, "PidsLimit": 32, "RestartPolicy": {"Name": "no"}},
                "Config": {"User": "65532:65532", "Env": ["YNAB_ALLOW_WRITES=0", "YNAB_DISABLE_AGENT_CONFIG_FALLBACK=1"]},
                "Mounts": [], "networks": {"ynab_mcp_private": "172.30.89.3"}, "running": True,
                "aliases": {"ynab_mcp_private": ["ynab-mcp-gateway"]}, "Image": "image-id"}
        with patch.object(app, "directory", return_value=Path("fixture")), \
             patch.object(release.common, "read", return_value=model), \
             patch.object(release.common, "inspect", return_value={"Id": "image-id"}), \
             patch.object(release, "runtime", return_value={"gateway": live}):
            record = {"images": {"gateway": "fixture-image"}}
            app.ownership([record])
            for field, value in (("CapAdd", ["NET_ADMIN"]), ("SecurityOpt", ["no-new-privileges:true", "seccomp=unconfined"]),
                                 ("SecurityOpt", ["no-new-privileges:false"])):
                with patch.dict(live["HostConfig"], {field: value}), self.assertRaises(release.common.ReleaseError):
                    app.ownership([record])
            live["aliases"] = {}
            with self.assertRaisesRegex(release.common.ReleaseError, "ownership"):
                app.ownership([record])


@unittest.skipIf(os.name == "nt", "Linux ownership, flock and fsync contract")
class AppReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ynab-release-state-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)
        for name in ("releases", "records", "attempts", "locks"):
            (self.root / name).mkdir(mode=0o700)
        for name in ("maintenance.lock", "ynab-mcp.lock"):
            (self.root / "locks" / name).touch(mode=0o600)
        self.live, self.events = {}, []
        self.serial = 0
        self.app = release.Release(self.root, Path("scanner"), Path("cache"))
        self.patches = [patch.object(release, "runtime", side_effect=lambda: copy.deepcopy(self.live)),
            patch.object(release, "companions", return_value={"notoli": "unchanged", "certificates": "unchanged"}),
            patch.object(release, "topology", return_value={"existing": "same-network-id"}),
            patch.object(release, "preflight", side_effect=lambda *args: self.events.append("paired-fresh-scan")),
            patch.object(release.Release, "stage", autospec=True, side_effect=self.stage),
            patch.object(release.Release, "compose", autospec=True, side_effect=self.compose),
            patch.object(release.Release, "ownership"), patch.object(release.Release, "ready")]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def images(self, source):
        return {role: "ghcr.io/fixture/" + role + "@sha256:" + source[0] * 64 for role in release.NAMES}

    def stage(self, app, source, images, secrets):
        self.events.append("stage")
        directory = self.root / "releases" / (source + "-" + uuid.uuid4().hex)
        directory.mkdir(mode=0o700)
        release.common.atomic(directory / "model.json", {"source": source,
            "services": {role: {"image": image} for role, image in images.items()}})
        return {"id": directory.name, "source": source, "directory": str(directory),
                "images": images, "files": release.files_identity(directory)}

    def compose(self, app, directory, *arguments):
        self.events.append(arguments[0])
        if arguments[0] == "up":
            self.serial += 1
            self.live = {role: {"image": json.loads((directory / "model.json").read_text())["source"],
                               "instance": self.serial, "running": True} for role in release.NAMES}
        else:
            self.live = {role: dict(value, running=False) for role, value in self.live.items()}

    def deploy(self, source, **kwargs):
        return self.app.deploy(source, self.images(source), {}, **kwargs)

    def test_scan_failure_precedes_staging_and_every_app_mutation(self):
        with patch.object(release, "preflight", side_effect=ValueError("stale or failed artifact")):
            with self.assertRaises(ValueError):
                self.deploy(SOURCE, initial=True)
        self.assertEqual(self.events, [])
        self.assertFalse((self.root / "pending.json").exists())
        self.assertEqual(list((self.root / "releases").iterdir()), [])

    def test_upgrade_and_explicit_rollback_restore_exact_prior_files_images(self):
        self.deploy(SOURCE, initial=True)
        first = release.common.read(self.root / "current.json")
        self.deploy(SECOND)
        self.assertEqual(self.events, ["paired-fresh-scan", "stage", "up"] * 2)
        self.app.rollback(outcome_confirmed=True)
        restored = release.common.read(self.root / "current.json")
        self.assertEqual(restored["source"], SOURCE)
        self.assertEqual(restored["images"], first["images"])
        self.assertEqual(restored["files"], first["files"])
        self.assertNotEqual(restored["runtime"], first["runtime"])
        self.assertFalse((self.root / "pending.json").exists())
        self.assertEqual(len(list((self.root / "attempts").iterdir())), 3)
        self.assertEqual(self.events[-2:], ["paired-fresh-scan", "up"])

    def test_staging_is_inactive_and_promotion_requires_a_second_fresh_scan(self):
        identity = self.app.stage_only(SOURCE, self.images(SOURCE), {})
        self.assertEqual(self.live, {})
        self.assertFalse((self.root / "current.json").exists())
        self.assertEqual(self.events, ["paired-fresh-scan", "stage"])
        self.app.promote(identity, initial=True)
        self.assertEqual(self.events[-2:], ["paired-fresh-scan", "up"])
        with self.assertRaises(release.common.ReleaseError):
            self.app.promote(identity)

    def test_staged_record_cannot_scan_different_images_from_compose(self):
        identity = self.app.stage_only(SOURCE, self.images(SOURCE), {})
        path = self.root / "records" / (identity + ".json")
        record = release.common.read(path)
        record["images"] = self.images(SECOND)
        release.common.atomic(path, record)
        before = list(self.events)
        with self.assertRaisesRegex(release.common.ReleaseError, "Compose model"):
            self.app.promote(identity, initial=True)
        self.assertEqual(self.events, before)
        self.assertFalse((self.root / "pending.json").exists())

    def test_interrupted_mutation_blocks_new_process_until_confirmed_recovery(self):
        self.deploy(SOURCE, initial=True)
        def interrupted(app, directory, *arguments):
            self.compose(app, directory, *arguments)
            raise release.common.CommandTimeout("Daemon outcome unknown")
        with patch.object(release.Release, "compose", new=interrupted):
            with self.assertRaises(release.common.ReleaseError):
                self.deploy(SECOND)
        barrier = release.common.read(self.root / "pending.json")
        self.assertEqual(barrier["phase"], "switching")
        reopened = release.Release(self.root, Path("scanner"), Path("cache"))
        before = list(self.events)
        with self.assertRaises(release.common.ReleaseError):
            reopened.deploy(SECOND, self.images(SECOND), {})
        with self.assertRaises(release.common.ReleaseError):
            reopened.recover()
        self.assertEqual(self.events, before)
        reopened.recover(outcome_confirmed=True)
        self.assertEqual(release.common.read(self.root / "current.json")["source"], SOURCE)
        self.assertFalse((self.root / "pending.json").exists())

    def test_changed_recovery_files_cannot_be_replayed(self):
        self.deploy(SOURCE, initial=True)
        first = release.common.read(self.root / "current.json")
        self.deploy(SECOND)
        (Path(first["directory"]) / "model.json").write_text("tampered")
        before = list(self.events)
        with self.assertRaises(release.common.ReleaseError):
            self.app.rollback(outcome_confirmed=True)
        self.assertEqual(self.events, before)

    def test_newly_failing_previous_artifact_scan_blocks_rollback_start(self):
        self.deploy(SOURCE, initial=True)
        self.deploy(SECOND)
        before = list(self.events)
        with patch.object(release, "preflight", side_effect=ValueError("new advisory")):
            with self.assertRaises(ValueError):
                self.app.rollback(outcome_confirmed=True)
        self.assertEqual(self.events, before)
        self.assertTrue((self.root / "pending.json").exists())
        self.assertEqual(release.common.read(self.root / "current.json")["source"], SECOND)

    def test_initial_failure_recovers_to_stopped_and_can_be_redeployed(self):
        with patch.object(release.Release, "ready", side_effect=release.common.ReleaseError("not ready")):
            with self.assertRaises(release.common.ReleaseError):
                self.deploy(SOURCE, initial=True)
        before = list(self.events)
        with self.assertRaises(release.common.ReleaseError):
            self.app.recover(outcome_confirmed=True)
        self.assertEqual(self.events, before)
        with patch.object(release, "preflight", side_effect=ValueError("artifact rejected")):
            self.app.recover(outcome_confirmed=True, stop_only=True)
        self.assertEqual(self.events[len(before):], ["stop"])
        self.assertTrue(release.common.read(self.root / "current.json")["disabled"])
        self.assertTrue(all(not value["running"] for value in self.live.values()))
        self.deploy(SECOND)
        self.assertFalse(release.common.read(self.root / "current.json")["disabled"])

    def test_initial_rollback_requires_explicit_stop_only_disable(self):
        self.deploy(SOURCE, initial=True)
        before = list(self.events)
        with self.assertRaises(release.common.ReleaseError):
            self.app.rollback(outcome_confirmed=True)
        self.assertEqual(self.events, before)
        self.assertFalse((self.root / "pending.json").exists())
        with patch.object(release, "preflight", side_effect=ValueError("artifact rejected")):
            self.app.disable(outcome_confirmed=True)
        self.assertEqual(self.events[len(before):], ["stop"])
        self.assertTrue(release.common.read(self.root / "current.json")["disabled"])
        self.assertTrue(all(not value["running"] for value in self.live.values()))

    def test_stop_only_flag_cannot_replace_fresh_scanned_active_recovery(self):
        self.deploy(SOURCE, initial=True)
        self.deploy(SECOND)
        with patch.object(release.Release, "recover"):
            self.app.rollback(outcome_confirmed=True)
        before = list(self.events)
        with self.assertRaises(release.common.ReleaseError):
            self.app.recover(outcome_confirmed=True, stop_only=True)
        self.assertEqual(self.events, before)
        self.app.recover(outcome_confirmed=True)
        self.assertEqual(self.events[-2:], ["paired-fresh-scan", "up"])

    def test_shared_maintenance_and_exclusive_app_lock_preserve_existing_inode(self):
        directory = self.root / "locks"
        path = directory / "maintenance.lock"
        inode = path.stat().st_ino
        with release.locks(directory):
            with release.common.maintenance(path, shared=True):
                pass
            with self.assertRaises(release.common.ReleaseError):
                with release.common.maintenance(path):
                    self.fail("Gateway maintenance entered an app release")
            with self.assertRaises(release.common.ReleaseError):
                with release.locks(directory):
                    self.fail("A second app release entered")
        self.assertEqual(path.stat().st_ino, inode)


if __name__ == "__main__":
    unittest.main(verbosity=2)
