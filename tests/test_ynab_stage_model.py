"""Real canonical Compose staging and secret preflight; no daemon mutations."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ynab_release as release


@unittest.skipUnless(os.name == "posix" and os.geteuid() == 0 and shutil.which("docker"),
                     "Linux root-owned synthetic secret metadata and Compose CLI required")
class CanonicalStageModel(unittest.TestCase):
    def setUp(self):
        # /tmp is intentionally forbidden by the production secret ancestor policy.
        self.temporary = tempfile.TemporaryDirectory(prefix="ynab-stage-model-", dir=Path.home())
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)
        for name in ("releases", "records", "attempts", "inputs"):
            (self.root / name).mkdir(mode=0o700)
        (self.root / "data").mkdir(mode=0o700)
        os.chown(self.root / "data", 65532, 65532)
        self.addCleanup(setattr, release.common, "DIAGNOSTICS", release.common.DIAGNOSTICS)
        self.app = release.Release(self.root)
        self.source = "a" * 40
        self.images = {role: "ghcr.io/fixture/" + role + "@sha256:" + ("a" if role == "gateway" else "b") * 64
                       for role in release.NAMES}
        # Standard-library fixture key generation is delegated to maintained OpenSSL;
        # the production preflight checks only PEM type/secret metadata at this phase.
        result = subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048"],
                                capture_output=True, check=True)
        public = subprocess.run(["openssl", "pkey", "-pubout"], input=result.stdout, capture_output=True, check=True).stdout
        values = {"ynab_api_token": b"synthetic-financial-token-never-used",
                  "gateway_identity.json": json.dumps({"issuer": "https://auth.judeandrewalaba.com",
                      "owner": "synthetic-central-owner", "clients": ["ynab-chatgpt", "ynab-codex"]}).encode(),
                  "oauth_public_key.pem": public}
        self.secrets = {}
        for name, value in values.items():
            path = self.root / "inputs" / name
            path.write_bytes(value)
            os.chown(path, 65532, 65532)
            path.chmod(0o400)
            self.secrets[name] = path
        recipe = {name: (release.REPO / relative).read_text() for name, relative in release.FILES.items()}
        self.source_provider = patch.object(release, "source_files", return_value=recipe)
        self.source_provider.start()
        self.addCleanup(self.source_provider.stop)
        self.raw_models = []
        self.real_run = subprocess.run
        self.override_memory = False

    def compose(self, command, **kwargs):
        self.assertEqual(command[:2], ["docker", "compose"])
        self.assertEqual(command[-3:], ["config", "--format", "json"])
        result = self.real_run(command, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.raw_models.append(json.loads(result.stdout))
        if self.override_memory:
            model = json.loads(result.stdout)
            model["services"]["gateway"]["mem_limit"] = self.memory_value
            return subprocess.CompletedProcess(result.args, result.returncode, json.dumps(model), result.stderr)
        return result

    def stage(self):
        with patch.object(release.subprocess, "run", side_effect=self.compose):
            return self.app.stage(self.source, self.images, self.secrets)

    def live(self, model):
        live = {}
        for role, expected in model["services"].items():
            live[role] = {"HostConfig": {"ReadonlyRootfs": True, "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges:true"], "Memory": int(expected["mem_limit"]),
                "PidsLimit": expected["pids_limit"], "NanoCpus": round(float(expected["cpus"]) * 1e9),
                "RestartPolicy": {"Name": "no"}},
                "Config": {"User": expected["user"], "Env":
                    ["YNAB_ALLOW_WRITES=" + release.write_mode(expected), "YNAB_DISABLE_AGENT_CONFIG_FALLBACK=1"] if role == "gateway" else []},
                "Mounts": [{"Type": "bind", "Destination": mount["target"], "Source": mount["source"],
                            "RW": not mount.get("read_only", False)} for mount in expected["volumes"]],
                "networks": {model["networks"][key]["name"]: value["ipv4_address"] for key, value in expected["networks"].items()},
                "aliases": {model["networks"][key]["name"]: value.get("aliases", []) for key, value in expected["networks"].items()},
                "Image": "synthetic-" + role, "running": True}
        return live

    def test_real_compose_stage_normalizes_memory_for_exact_docker_ownership(self):
        record = self.stage()
        model = release.common.read(self.app.directory(record) / "model.json")
        for role, memory in (("gateway", 512 * 1024**2), ("egress", 128 * 1024**2)):
            self.assertEqual(int(self.raw_models[0]["services"][role]["mem_limit"]), memory)
            self.assertIs(type(model["services"][role]["mem_limit"]), int)
            self.assertEqual(model["services"][role]["mem_limit"], memory)
            expected = copy.deepcopy(self.raw_models[0]["services"][role])
            expected["mem_limit"] = memory
            self.assertEqual(model["services"][role], expected)
        self.assertEqual(model["networks"], self.raw_models[0]["networks"])
        for path in (Path(record["directory"]) / "secrets").iterdir():
            self.assertEqual(path.stat().st_uid, 65532)
            self.assertEqual(path.stat().st_mode & 0o777, 0o400)
        live = self.live(model)
        with patch.object(release, "runtime", return_value=live), patch.object(release.common, "inspect",
                side_effect=lambda kind, image: {"Id": "synthetic-" + next(role for role in self.images if self.images[role] == image)}):
            self.app.ownership([record])
            self.assertEqual(release.write_mode(model["services"]["gateway"]), "1")
            self.assertEqual(record["journal"], self.app.journal_identity())
            self.assertIn({"Type": "bind", "Destination": "/data", "Source": str(self.root / "data"), "RW": True},
                          live["gateway"]["Mounts"])
            with patch.dict(live["gateway"]["Config"], {"Env": ["YNAB_ALLOW_WRITES=0", "YNAB_DISABLE_AGENT_CONFIG_FALLBACK=1"]}), \
                    self.assertRaisesRegex(release.common.ReleaseError, "ownership"):
                self.app.ownership([record])
            for role in release.NAMES:
                live[role]["HostConfig"]["Memory"] += 1
                with self.assertRaisesRegex(release.common.ReleaseError, "ownership"):
                    self.app.ownership([record])
                live[role]["HostConfig"]["Memory"] -= 1

    def test_journal_directory_must_be_provisioned_and_retains_identity(self):
        journal = self.root / "data"
        journal.chmod(0o755)
        with self.assertRaisesRegex(release.common.ReleaseError, "journal directory"):
            self.stage()
        journal.chmod(0o700)
        record = self.stage()
        journal.rename(self.root / "retained-journal")
        journal.mkdir(mode=0o700)
        os.chown(journal, 65532, 65532)
        with self.assertRaisesRegex(release.common.ReleaseError, "directory changed"):
            self.app.directory(record)
        journal.rmdir()
        journal.symlink_to(self.root / "retained-journal", target_is_directory=True)
        with self.assertRaisesRegex(release.common.ReleaseError, "journal directory"):
            self.app.directory(record)

    def test_invalid_secret_metadata_fails_before_compose(self):
        self.secrets["ynab_api_token"].chmod(0o600)
        with patch.object(release.subprocess, "run", side_effect=AssertionError("Compose must not run")), self.assertRaises(ValueError):
            self.app.stage(self.source, self.images, self.secrets)
        self.assertFalse(list((self.root / "releases").iterdir()))

    def test_noncanonical_memory_types_are_not_coerced_into_valid_models(self):
        self.override_memory = True
        for self.memory_value in (True, 536870912.0, "512m", "0", "-1", None, "５１２"):
            with self.subTest(value=self.memory_value), self.assertRaisesRegex(release.common.ReleaseError, "memory limit"):
                self.stage()
        self.assertFalse(list((self.root / "releases").rglob("model.json")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
