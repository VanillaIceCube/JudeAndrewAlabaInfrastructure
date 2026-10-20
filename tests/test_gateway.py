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
    def test_pending_preflight_allows_absent_gateway_without_weakening_app_trust(self):
        objects = {}
        for name, (internal, subnet, apps) in release.check_host.NETWORKS.items():
            objects[("network", name)] = {"Internal": internal, "IPAM": {"Config": [{"Subnet": subnet}]},
                "Containers": {app: {"Name": app, "IPv4Address": "172.30.88.3/29"} for app in apps}}
        for name in ("notoli-backend", "macromapper-backend"):
            objects[("container", name)] = {"Config": {"Env": ["DJANGO_TRUSTED_PROXY_IPS=172.30.88.2"]},
                                           "HostConfig": {"PortBindings": {}}}
        with patch.object(release.check_host, "inspect", side_effect=lambda kind, name: copy.deepcopy(objects[(kind, name)])), \
                patch("sys.stdout", new_callable=io.StringIO):
            release.check_host.verify("host", allow_missing_proxy=True)
            with self.assertRaises(ValueError):
                release.check_host.verify("host")
            # An interrupted creation may have attached the proxy to only one network.
            members = objects[("network", "notoli_backend_private")]["Containers"]
            members["gateway"] = {"Name": "host-ingress-proxy", "IPv4Address": "172.30.88.2/29"}
            release.check_host.verify("host", allow_missing_proxy=True)
            members["gateway"]["IPv4Address"] = "172.30.88.4/29"
            with self.assertRaises(ValueError):
                release.check_host.verify("host", allow_missing_proxy=True)
            del members["gateway"]
            objects[("container", "notoli-backend")]["Config"]["Env"] = []
            with self.assertRaises(ValueError):
                release.check_host.verify("host", allow_missing_proxy=True)

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

    def test_run_evidence_preserves_promoted_and_running_identities_without_deployment_api(self):
        for operation, status, running in (("deploy", "success", SOURCE),
                                            ("deploy", "unchanged", SECOND),
                                            ("rollback", "rolled_back", SECOND)):
            with self.subTest(operation=operation, status=status), tempfile.TemporaryDirectory() as temporary:
                summary = Path(temporary) / "summary"
                env = {"GITHUB_STEP_SUMMARY": str(summary), "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1",
                       "GATEWAY_OPERATION": operation,
                       "GATEWAY_RECOVERY": SECOND + "-1-1" if operation == "rollback" else ""}
                with patch.dict(os.environ, env), patch.object(transport, "authorization", return_value=SOURCE), \
                        patch.object(transport, "api") as api, patch("sys.stdout", new_callable=io.StringIO), \
                        patch.object(transport, "execute", return_value={"status": status, "running_source": running}):
                    transport.main()
                api.assert_not_called()
                text = summary.read_text()
                self.assertIn("promoted source `" + SOURCE + "`", text)
                self.assertIn("running source `" + running + "`", text)
                self.assertIn("**" + status + "**", text)
                if operation == "rollback":
                    self.assertIn("Explicit recovery target: `" + SECOND + "-1-1`", text)

    def test_failed_transport_never_asserts_acceptance_or_leaks_private_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            summary = Path(temporary) / "summary"
            env = {"GITHUB_STEP_SUMMARY": str(summary), "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1",
                   "GATEWAY_OPERATION": "deploy", "GATEWAY_RECOVERY": ""}
            with patch.dict(os.environ, env), patch.object(transport, "authorization", return_value=SOURCE), \
                    patch.object(transport, "execute", side_effect=subprocess.TimeoutExpired("private-key", 1)), \
                    patch("sys.stdout", new_callable=io.StringIO):
                with self.assertRaises(subprocess.TimeoutExpired):
                    transport.main()
                transport.finalize_failure()
            text = summary.read_text()
            self.assertIn("runner failed", text)
            self.assertIn("host outcome is unconfirmed", text)
            self.assertNotIn("Verified host result", text)
            self.assertNotIn("private-key", text)

    def test_invalid_operation_or_recovery_cannot_start_transport(self):
        for operation, recovery in (("other", ""), ("deploy", SECOND + "-1-1"),
                                     ("rollback", ""), ("rollback", "private-invalid-input")):
            env = {"GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1",
                   "GATEWAY_OPERATION": operation, "GATEWAY_RECOVERY": recovery}
            with self.subTest(operation=operation, recovery=recovery), patch.dict(os.environ, env), \
                    patch.object(transport, "authorization", return_value=SOURCE), \
                    patch.object(transport, "execute") as execute, patch.object(transport, "evidence") as evidence:
                with self.assertRaises(release.ReleaseError):
                    transport.main()
                execute.assert_not_called()
                evidence.assert_not_called()

    def test_rollback_transport_uploads_helpers_without_building_a_source_archive(self):
        calls = []
        def run(args, timeout=120):
            calls.append(list(map(str, args)))
            if str(args[-1]).startswith("systemd-run "):
                return json.dumps({"status": "rolled_back", "running_source": SOURCE, "private": "fixture-only"})
            return ""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch.dict(os.environ, {"GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SERVER_URL": "https://github.com"}), \
                    patch.object(transport, "ssh_configuration", return_value=directory / "config"), \
                    patch.object(transport, "run", side_effect=run):
                result = transport.execute(SOURCE, "rollback", SECOND + "-9-1", directory)
            self.assertEqual(result, {"status": "rolled_back", "running_source": SOURCE})
            self.assertFalse(any(args[0] == "git" for args in calls))
            self.assertEqual([Path(args[-2]).as_posix() for args in calls if args[0] == "scp"],
                             ["scripts/gateway_release.py", "scripts/check_host.py"])
            self.assertFalse((directory / "source.tar").exists())
            self.assertIn("--id " + SECOND + "-9-1", calls[-1][-1])

    def test_cancelled_runner_finalizer_never_calls_api_or_host_or_overwrites_acceptance(self):
        for state in ("failure", "cancelled"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                summary = Path(temporary) / "summary"
                summary.write_text("Verified host result: **success**; running source `" + SOURCE + "`.\n")
                with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary), "GATEWAY_RUNNER_STATUS": state}), \
                        patch.object(transport, "api") as api, patch.object(transport, "run") as run, \
                        patch("sys.stdout", new_callable=io.StringIO):
                    transport.finalize_failure()
                api.assert_not_called()
                run.assert_not_called()
                self.assertIn("runner " + ("cancelled" if state == "cancelled" else "failed"), summary.read_text())
                self.assertIn("Verified host result: **success**", summary.read_text())
                self.assertIn("host outcome is unconfirmed", summary.read_text())

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

    def test_authorization_rejects_main_pr_stale_source_and_disabled_deployment(self):
        env = {"GITHUB_REPOSITORY": transport.REPOSITORY, "GITHUB_REF": "refs/heads/env-prod",
               "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": SOURCE, "DEPLOY_ENABLED": "true",
               "GITHUB_ACTOR": "VanillaIceCube", "GITHUB_TRIGGERING_ACTOR": "VanillaIceCube",
               "GITHUB_WORKFLOW_REF": transport.REPOSITORY + "/.github/workflows/deploy-gateway.yml@refs/heads/env-prod",
               "GITHUB_WORKFLOW_SHA": SOURCE}
        for key, value in (("GITHUB_REF", "refs/heads/main"), ("GITHUB_EVENT_NAME", "pull_request"),
                           ("DEPLOY_ENABLED", "false"), ("GITHUB_ACTOR", "other-user"),
                           ("GITHUB_TRIGGERING_ACTOR", "other-user"),
                           ("GITHUB_REPOSITORY", "other/repo"), ("GITHUB_SHA", "invalid"),
                           ("GITHUB_WORKFLOW_SHA", SECOND),
                           ("GITHUB_WORKFLOW_REF", transport.REPOSITORY + "/.github/workflows/other.yml@refs/heads/env-prod"),
                           ("GITHUB_WORKFLOW_REF", transport.REPOSITORY + "/.github/workflows/deploy-gateway.yml@refs/heads/main")):
            with self.subTest(key=key), patch.dict(os.environ, {**env, key: value}, clear=True), \
                    self.assertRaises(release.ReleaseError):
                transport.authorization()
        with patch.dict(os.environ, env, clear=True), patch.object(transport, "run", return_value=SOURCE), \
                patch.object(transport, "api", return_value={"object": {"sha": SECOND}}), \
                self.assertRaises(release.ReleaseError):
            transport.authorization()

    def test_promotion_merge_requires_exact_reviewed_tree_when_not_in_main_history(self):
        env = {"GITHUB_REPOSITORY": transport.REPOSITORY, "GITHUB_REF": "refs/heads/env-prod",
               "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": SOURCE, "DEPLOY_ENABLED": "true",
               "GITHUB_ACTOR": "VanillaIceCube", "GITHUB_TRIGGERING_ACTOR": "VanillaIceCube",
               "GITHUB_WORKFLOW_REF": transport.REPOSITORY + "/.github/workflows/deploy-gateway.yml@refs/heads/env-prod",
               "GITHUB_WORKFLOW_SHA": SOURCE}
        for relationship, matching, allowed in (("behind", True, True), ("diverged", True, True),
                                                ("behind", False, False), ("diverged", False, False),
                                                ("ahead", False, True), ("identical", False, True)):
            with self.subTest(relationship=relationship, matching=matching):
                def api(endpoint):
                    if endpoint.endswith("/heads/env-prod"):
                        return {"object": {"sha": SOURCE}}
                    if endpoint.endswith("/heads/main"):
                        return {"object": {"sha": SECOND}}
                    if "/compare/" in endpoint:
                        return {"status": relationship}
                    if endpoint.endswith("/git/commits/" + SOURCE):
                        return {"tree": {"sha": "c" * 40}}
                    if endpoint.endswith("/git/commits/" + SECOND):
                        return {"tree": {"sha": ("c" if matching else "d") * 40}}
                    self.fail("Unexpected non-source API call: " + endpoint)
                with patch.dict(os.environ, env, clear=True), patch.object(transport, "run", return_value=SOURCE), \
                        patch.object(transport, "api", side_effect=api):
                    if allowed:
                        self.assertEqual(transport.authorization(), SOURCE)
                    else:
                        with self.assertRaises(release.ReleaseError):
                            transport.authorization()

    def test_ssh_pins_the_negotiated_host_key_including_rsa_sha2(self):
        for encoding, algorithm in (("ssh-ed25519", "ssh-ed25519"), ("ssh-rsa", "rsa-sha2-512")):
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory() as temporary:
                env = {"DEPLOY_HOST": "host.example", "DEPLOY_USER": "root", "DEPLOY_PORT": "22",
                       "DEPLOY_SSH_KEY": "fixture\r\n",
                       "DEPLOY_HOST_FINGERPRINT": "SHA256:fixture"}
                def discovery(args, **kwargs):
                    if args[0] == "ssh-keyscan":
                        return "host.example " + encoding + " AAAA\nhost.example ssh-ed25519 BBBB\n"
                    return "256 SHA256:" + ("fixture" if "AAAA" in (Path(args[2]).read_text()) else "other") + " comment"
                with patch.object(transport, "run", side_effect=discovery):
                    path = transport.ssh_configuration(Path(temporary), env)
                self.assertIn("HostKeyAlgorithms " + algorithm, path.read_text())
                self.assertIn("StrictHostKeyChecking yes", path.read_text())
                self.assertEqual((Path(temporary) / "key").read_bytes(), b"fixture\n")
                self.assertEqual((Path(temporary) / "known_hosts").read_text(), "gateway-host " + encoding + " AAAA\n")
                env["DEPLOY_HOST_FINGERPRINT"] = "SHA256:wrong"
                with patch.object(transport, "run", side_effect=discovery), \
                        self.assertRaises(release.ReleaseError):
                    transport.ssh_configuration(Path(temporary), env)
        with tempfile.TemporaryDirectory() as temporary, patch.object(transport, "run", return_value=""), \
                self.assertRaises(release.ReleaseError):
            transport.ssh_configuration(Path(temporary), env)
        with tempfile.TemporaryDirectory() as temporary, \
                patch.dict(os.environ, {**env, "GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "1"}), \
                patch.object(transport, "run", return_value="") as commands, \
                self.assertRaises(release.ReleaseError):
            transport.execute(SOURCE, "deploy", "", Path(temporary))
        self.assertEqual([call.args[0][0] for call in commands.call_args_list], ["ssh-keyscan"])

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

    def test_pending_recovery_refreshes_rebooted_app_identities_before_restoration(self):
        self.prepare_old()
        def kill(directory, *args):
            if args[0] == "up":
                raise KeyboardInterrupt()
        self.gateway.compose.side_effect = kill
        with self.assertRaises(KeyboardInterrupt):
            self.deploy()
        self.mocks[5].return_value = {"apps": "restarted-after-reboot", "networks": "unchanged"}
        self.gateway.compose.side_effect = self.compose
        self.gateway.rollback(self.identity, None)
        self.assertFalse((self.root / "pending.json").exists())
        self.assertEqual(release.read(self.root / "current.json")["source"], SOURCE)
        self.assertIn(unittest.mock.call(allow_missing_proxy=True), self.mocks[5].call_args_list)

    def test_pending_recovery_rejects_recreated_networks_before_gateway_mutation(self):
        self.prepare_old()
        def kill(directory, *args):
            if args[0] == "up":
                raise KeyboardInterrupt()
        self.gateway.compose.side_effect = kill
        with self.assertRaises(KeyboardInterrupt):
            self.deploy()
        self.mocks[5].return_value = {"apps": "restarted-after-reboot", "networks": "recreated"}
        self.gateway.compose.side_effect = self.compose
        with self.assertRaisesRegex(release.ReleaseError, "network IDs changed"):
            self.gateway.rollback(self.identity, None)
        self.assertFalse(any(args[0] == "up" for _, args in self.calls))
        self.assertTrue((self.root / "pending.json").exists())

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
