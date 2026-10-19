"""Gateway transaction, authorization, host-key and crash-barrier regressions."""

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gateway_release as release
import gateway_transport as transport

SOURCE = "a" * 40
SECOND = "b" * 40


def archive(path, content="events {}\nhttp {}\n"):
    with tarfile.open(path, "w") as target:
        for name, data in {"compose.yml": "{}", "nginx/nginx.conf": content}.items():
            item = tarfile.TarInfo(name)
            item.size = len(data.encode())
            target.addfile(item, io.BytesIO(data.encode()))


class AuthorizationTests(unittest.TestCase):
    def test_cached_immutable_image_needs_no_registry_pull(self):
        image = "nginx@sha256:" + "c" * 64
        with patch.object(release, "inspect", return_value={"RepoDigests": [image]}), \
                patch.object(release, "docker") as docker:
            release.ensure_image(image)
        docker.assert_not_called()
        with patch.object(release, "inspect", return_value={"RepoDigests": []}), \
                self.assertRaises(release.ReleaseError):
            release.ensure_image(image)

    @unittest.skipIf(os.name == "nt", "Linux evidence ownership contract")
    def test_failed_command_retains_bounded_private_diagnostics_without_public_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch.object(release, "DIAGNOSTICS", directory):
                with self.assertRaises(release.ReleaseError) as error:
                    release.run([sys.executable, "-c", "import sys; sys.stderr.write('fixture-only-' * 2000); sys.exit(7)"])
            self.assertNotIn("fixture-only", str(error.exception))
            files = list(directory.glob("*.json"))
            self.assertEqual(len(files), 1)
            self.assertEqual(len(release.read(files[0])["stderr"]), 8192)
            self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)

    def test_exact_status_payload_and_explicit_retirement_of_production_successes(self):
        calls = []
        def api(endpoint, method="GET", data=None):
            calls.append((endpoint, method, data))
            if "?environment=" in endpoint:
                return [{"id": 10, "production_environment": True}, {"id": 11}]
            if endpoint.endswith("?per_page=1"):
                return [{"state": "success"}]
            return None
        with patch.dict(os.environ, {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_RUN_ID": "42"}), \
                patch.object(transport, "api", side_effect=api):
            transport.status(11, "success", "Verified running gateway")
        payloads = [data for endpoint, method, data in calls if method == "POST"]
        self.assertEqual(payloads[0], {"state": "success", "description": "Verified running gateway",
                         "log_url": "https://github.com/" + transport.REPOSITORY + "/actions/runs/42", "auto_inactive": False})
        self.assertEqual(payloads[1]["state"], "inactive")
        self.assertIn("/deployments/10/statuses", calls[-1][0])

    def test_deployment_tracking_uses_restored_source_and_never_labels_failed_promotion_successful(self):
        env = {"GITHUB_OUTPUT": "", "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1",
               "GATEWAY_OPERATION": "rollback", "GATEWAY_RECOVERY": SECOND + "-1-1"}
        calls = []
        def api(endpoint, method="GET", data=None):
            calls.append((endpoint, data))
            return {"id": 11 if len(calls) == 1 else 12}
        with tempfile.TemporaryDirectory() as temporary:
            env["GITHUB_OUTPUT"] = str(Path(temporary) / "output")
            with patch.dict(os.environ, env), patch.object(transport, "authorization", return_value=SECOND), \
                    patch.object(transport, "api", side_effect=api), patch.object(transport, "status") as status, \
                    patch.object(transport, "execute", return_value={"status": "rolled_back", "running_source": SOURCE}):
                transport.main()
            self.assertEqual([data["ref"] for endpoint, data in calls if endpoint.endswith("/deployments")], [SECOND, SOURCE])
            self.assertFalse(any(args.args[:2] == (11, "success") for args in status.call_args_list))
            self.assertEqual(status.call_args_list[-1].args[1], "success")
            self.assertIn(SOURCE, status.call_args_list[-1].args[2])

    def test_health_checks_edge_and_origin_with_tls_assertions_and_honest_identity(self):
        connections = []
        class Connection:
            def __init__(self, domain, **kwargs):
                self.domain = domain
                self.kwargs = kwargs
                connections.append(self)
            def request(self, method, path, headers):
                self.path, self.headers = path, headers
            def getresponse(self):
                domain = "https://" + self.domain
                if self.path == "/":
                    status, body, headers = 200, b"<html>ready</html>", {}
                elif self.path == "/api/notifications/":
                    status, body, headers = 401, b'{"detail":"unauthenticated"}', {"Content-Type": "application/json"}
                elif self.path.endswith("oauth-authorization-server"):
                    status, body, headers = 200, json.dumps({"issuer": domain}).encode(), {}
                elif self.path.endswith("/mcp") and self.path != "/mcp":
                    status, body, headers = 200, json.dumps({"resource": domain + "/mcp"}).encode(), {}
                else:
                    status, body, headers = 401, b"", {"WWW-Authenticate": "Bearer resource_metadata=..."}
                result = type("Response", (), {"status": status, "read": lambda self, limit: body,
                                                "getheader": lambda self, key, default: headers.get(key, default)})()
                return result
            def close(self):
                pass
        with patch.object(release.http.client, "HTTPSConnection", Connection), \
                patch.object(release.ssl, "create_default_context", return_value="verified-context") as contexts:
            release.health_once("origin-ca.pem")
        self.assertEqual(contexts.call_args_list[0].kwargs, {"cafile": None})
        self.assertEqual(contexts.call_args_list[1].kwargs, {"cafile": "origin-ca.pem"})
        self.assertEqual(len(connections), 14)
        self.assertTrue(all(item.headers["User-Agent"] == "JudeGatewayRelease/1.0" for item in connections))
        self.assertFalse(hasattr(connections[0], "_create_connection"))
        self.assertTrue(hasattr(connections[-1], "_create_connection"))
        self.assertTrue(all(item.kwargs["context"] == "verified-context" for item in connections))

    def test_public_challenge_or_redirect_cannot_be_accepted_as_healthy(self):
        response = type("Response", (), {"status": 302, "read": lambda self, limit: b"<html>challenge</html>"})()
        connection = unittest.mock.Mock()
        connection.getresponse.return_value = response
        with patch.object(release.http.client, "HTTPSConnection", return_value=connection), \
                self.assertRaises(release.ReleaseError):
            release.health_once()

    def test_production_policy_rejects_missing_reviewers_self_approval_and_broad_branches(self):
        environment = {"deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True},
                       "can_admins_bypass": False,
                       "protection_rules": [{"type": "required_reviewers", "prevent_self_review": True,
                                             "reviewers": [{"id": 1}]}]}
        branches = {"branch_policies": [{"name": "env-prod", "type": "branch"}]}
        transport.policy(environment, branches)
        for key, value in (("can_admins_bypass", True), ("protection_rules", []),
                           ("deployment_branch_policy", None)):
            with self.subTest(key=key), self.assertRaises(release.ReleaseError):
                transport.policy({**environment, key: value}, branches)
        for field in ("reviewers", "prevent_self_review"):
            altered = copy.deepcopy(environment)
            altered["protection_rules"][0][field] = False
            with self.assertRaises(release.ReleaseError):
                transport.policy(altered, branches)
        with self.assertRaises(release.ReleaseError):
            transport.policy(environment, {"branch_policies": [{"name": "*", "type": "branch"}]})

    def test_authorization_rejects_main_pr_stale_source_and_missing_exact_approval(self):
        env = {"GITHUB_REPOSITORY": transport.REPOSITORY, "GITHUB_REF": "refs/heads/env-prod",
               "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": SOURCE, "GATEWAY_DEPLOY_ENABLED": "true",
               "GATEWAY_APPROVED_SHA": SOURCE}
        for key, value in (("GITHUB_REF", "refs/heads/main"), ("GITHUB_EVENT_NAME", "pull_request"),
                           ("GATEWAY_APPROVED_SHA", SECOND), ("GATEWAY_DEPLOY_ENABLED", "false")):
            with self.subTest(key=key), patch.dict(os.environ, {**env, key: value}, clear=True), \
                    self.assertRaises(release.ReleaseError):
                transport.authorization()
        with patch.dict(os.environ, env, clear=True), patch.object(transport, "run", return_value=SOURCE), \
                patch.object(transport, "api", return_value={"object": {"sha": SECOND}}), \
                self.assertRaises(release.ReleaseError):
            transport.authorization()

    def test_ssh_pins_the_negotiated_host_key_including_rsa_sha2(self):
        for encoding, algorithm in (("ssh-ed25519", "ssh-ed25519"), ("ssh-rsa", "rsa-sha2-512")):
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory() as temporary:
                env = {"GATEWAY_SSH_HOST": "host.example", "GATEWAY_SSH_USER": "root", "GATEWAY_SSH_PORT": "22",
                       "GATEWAY_SSH_KEY": "fixture", "GATEWAY_SSH_KNOWN_HOST": "gateway-host " + encoding + " AAAA",
                       "GATEWAY_SSH_FINGERPRINT": "SHA256:fixture"}
                with patch.object(transport, "run", return_value="256 SHA256:fixture comment"):
                    path = transport.ssh_configuration(Path(temporary), env)
                self.assertIn("HostKeyAlgorithms " + algorithm, path.read_text())
                self.assertIn("StrictHostKeyChecking yes", path.read_text())
                env["GATEWAY_SSH_FINGERPRINT"] = "SHA256:wrong"
                with patch.object(transport, "run", return_value="256 SHA256:fixture comment"), \
                        self.assertRaises(release.ReleaseError):
                    transport.ssh_configuration(Path(temporary), env)

    def test_bundle_rejects_traversal_symlink_and_duplicate(self):
        for kind in ("traversal", "symlink", "duplicate"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                with tarfile.open(root / "source.tar", "w") as target:
                    item = tarfile.TarInfo("../escape" if kind == "traversal" else "compose.yml")
                    if kind == "symlink":
                        item.type = tarfile.SYMTYPE
                        item.linkname = "/etc/passwd"
                    target.addfile(item, io.BytesIO())
                    if kind == "duplicate":
                        target.addfile(item, io.BytesIO())
                (root / "out").mkdir()
                with self.assertRaises(release.ReleaseError):
                    release.unpack(root / "source.tar", root / "out")
                self.assertFalse((root.parent / "escape").exists())

    def test_bundle_preserves_allowed_empty_configuration_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive(root / "source.tar")
            with tarfile.open(root / "source.tar", "a") as target:
                item = tarfile.TarInfo("nginx/snippets")
                item.type = tarfile.DIRTYPE
                target.addfile(item)
            (root / "out").mkdir()
            release.unpack(root / "source.tar", root / "out")
            self.assertTrue((root / "out/nginx/snippets").is_dir())


@unittest.skipIf(os.name == "nt", "Linux ownership, locking and fsync contract")
class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)
        for name in ("releases", "attempts", "incoming"):
            (self.root / name).mkdir(mode=0o700)
        self.gateway = release.Gateway(self.root)
        self.live = {"Id": "old", "Image": "old-image", "Mounts": [{"Source": "/certs", "Destination": "/etc/nginx/certs"}]}
        self.model = {"services": {"proxy": {"image": "nginx@sha256:" + "c" * 64, "volumes": []}}}
        self.previous_directory = self.root / "releases" / (SOURCE + "-0-0")
        self.previous_directory.mkdir(mode=0o700)
        release.atomic(self.previous_directory / "model.json", self.model)
        self.previous = {"source": SOURCE, "directory": str(self.previous_directory), "image": self.model["services"]["proxy"]["image"],
                         "configuration": "old-config", "runtime": self.live, "actions_run": "old-run", "recovery": None}
        release.atomic(self.root / "current.json", self.previous)
        self.identity = SECOND + "-1-1"
        self.bundle = self.root / "bundle.tar"
        archive(self.bundle)
        self.calls = []
        patches = [patch.object(self.gateway, "current", side_effect=lambda: release.read(self.root / "current.json")),
                   patch.object(self.gateway, "capacity"), patch.object(self.gateway, "syntax"),
                   patch.object(self.gateway, "compose", side_effect=self.compose),
                   patch.object(release, "runtime", side_effect=lambda: self.live.copy()),
                   patch.object(release, "invariants", return_value={"apps": "unchanged", "networks": "unchanged"}),
                   patch.object(release, "certificate_identity", return_value="unchanged"),
                   patch.object(release, "config_identity", side_effect=lambda model: "old-config" if model.get("old") else "new-config"),
                   patch.object(release, "validate_model"), patch.object(release, "healthy"),
                   patch.object(release, "inspect", return_value={"Id": "new-image"}),
                   patch.object(release, "docker"),
                   patch.object(release, "ensure_image"),
                   patch.object(release.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(self.model)))]
        self.mocks = [self.enterContext(item) for item in patches]

    def compose(self, directory, *args):
        self.calls.append((directory, args))
        if args[0] == "up":
            self.live = {**self.live, "Id": "new", "Image": "new-image"}
        return ""

    def deploy(self):
        return self.gateway.deploy(self.bundle, self.identity, "https://github.com/run/1", None)

    def prepare_old(self):
        release.atomic(self.previous_directory / "model.json", {**self.model, "old": True})

    def test_rejected_syntax_cannot_change_live_gateway_or_accepted_record(self):
        self.gateway.syntax.side_effect = release.ReleaseError("invalid nginx")
        with self.assertRaises(release.ReleaseError):
            self.deploy()
        self.assertFalse(any(args[0] == "up" for _, args in self.calls))
        self.assertEqual(release.read(self.root / "current.json"), self.previous)
        self.assertFalse((self.root / "pending.json").exists())

    def test_noop_records_promoted_and_running_sources_without_activation(self):
        self.mocks[7].side_effect = None
        self.mocks[7].return_value = "old-config"
        self.assertEqual(self.deploy(), {"status": "unchanged", "running_source": SOURCE})
        self.assertEqual(self.calls, [])
        self.assertEqual(release.read(self.root / "current.json"), self.previous)

    def test_failed_health_restores_previous_and_failure_is_visible(self):
        self.prepare_old()
        self.mocks[9].side_effect = [None, release.ReleaseError("unhealthy"), None]
        with self.assertRaisesRegex(release.ReleaseError, "previous gateway restored"):
            self.deploy()
        self.assertEqual(release.read(self.root / "current.json")["source"], SOURCE)
        self.assertEqual(release.read(self.root / "attempts" / self.identity / "result.json")["status"], "rolled_back")
        self.assertFalse((self.root / "pending.json").exists())
        self.assertEqual([path for path, args in self.calls if args[0] == "up"],
                         [self.root / "releases" / self.identity, self.previous_directory])

    def test_interrupted_activation_blocks_retry_until_explicit_recovery(self):
        self.prepare_old()
        def kill(directory, *args):
            if args[0] == "up":
                raise KeyboardInterrupt()
        self.gateway.compose.side_effect = kill
        with self.assertRaises(KeyboardInterrupt):
            self.deploy()
        self.assertTrue((self.root / "pending.json").exists())
        with self.assertRaisesRegex(release.ReleaseError, "Interrupted"):
            self.gateway.deploy(self.bundle, SECOND + "-1-2", "run", None)
        self.gateway.compose.side_effect = self.compose
        self.gateway.rollback(self.identity, None)
        self.assertFalse((self.root / "pending.json").exists())
        self.assertEqual(release.read(self.root / "current.json")["source"], SOURCE)

    def test_failed_rollback_retains_barrier(self):
        self.prepare_old()
        self.mocks[9].side_effect = [None, release.ReleaseError("unhealthy"), release.ReleaseError("recovery unhealthy")]
        with self.assertRaises(release.ReleaseError):
            self.deploy()
        self.assertTrue((self.root / "pending.json").exists())
        self.assertEqual(release.read(self.root / "current.json")["source"], SOURCE)

    def test_indeterminate_docker_timeout_keeps_barrier_instead_of_racing_rollback(self):
        def timeout(directory, *args):
            if args[0] == "up":
                raise release.CommandTimeout("daemon request outcome unknown")
        self.gateway.compose.side_effect = timeout
        with self.assertRaisesRegex(release.ReleaseError, "timed out"):
            self.deploy()
        self.assertTrue((self.root / "pending.json").exists())
        self.assertEqual(release.read(self.root / "current.json")["source"], SOURCE)

    def test_second_independent_release_and_explicit_rollback(self):
        self.prepare_old()
        self.assertEqual(self.deploy()["status"], "success")
        second_directory = self.root / "releases" / self.identity
        release.atomic(second_directory / "model.json", {**self.model, "old": True})
        self.mocks[7].side_effect = lambda model: "new-config" if model.get("old") else "next-config"
        self.identity = "d" * 40 + "-2-1"
        self.assertEqual(self.deploy()["running_source"], "d" * 40)
        self.gateway.rollback(self.identity, None)
        self.assertEqual(release.read(self.root / "current.json")["source"], SECOND)

    def test_shared_app_lock_excludes_gateway_and_stable_inode_survives_release(self):
        import fcntl
        directory = self.root / "locks"
        directory.mkdir(mode=0o700)
        lock = directory / "maintenance.lock"
        lock.touch(mode=0o600)
        inode = lock.stat().st_ino
        with lock.open("r+") as stream:
            fcntl.flock(stream, fcntl.LOCK_SH | fcntl.LOCK_NB)
            with self.assertRaisesRegex(release.ReleaseError, "already active"):
                with release.maintenance(lock):
                    self.fail("Gateway entered during app deployment")
        with release.maintenance(lock):
            with self.assertRaises(release.ReleaseError):
                with release.maintenance(lock):
                    self.fail("Overlapping gateway deployment")
        self.assertEqual(lock.stat().st_ino, inode)


if __name__ == "__main__":
    unittest.main()
