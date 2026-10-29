"""Optional gateway profile packaging, topology, health and transition policy."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gateway_profile as profiles
import gateway_release as release
import gateway_transport as transport


class ProfileTests(unittest.TestCase):
    def test_unknown_profile_is_rejected_before_source_api_or_credentials(self):
        env = {"GITHUB_REPOSITORY": transport.REPOSITORY, "GITHUB_REF": "refs/heads/env-prod",
               "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": "a" * 40, "DEPLOY_ENABLED": "true",
               "GITHUB_ACTOR": "VanillaIceCube", "GITHUB_TRIGGERING_ACTOR": "VanillaIceCube",
               "GITHUB_WORKFLOW_SHA": "a" * 40,
               "GITHUB_WORKFLOW_REF": transport.REPOSITORY + "/.github/workflows/deploy-gateway.yml@refs/heads/env-prod",
               "YNAB_ROUTE_PROFILE": "invalid-profile"}
        with patch.dict(os.environ, env, clear=True), patch.object(transport, "api") as api, patch.object(transport, "ssh_configuration") as ssh:
            with self.assertRaises(ValueError):
                transport.authorization()
        api.assert_not_called()
        ssh.assert_not_called()

    def test_transition_requires_tombstone_baseline_and_keeps_hostname_protection(self):
        for previous, candidate in (("base", "base"), ("base", "disabled"), ("disabled", "enabled"),
                                    ("enabled", "enabled"), ("enabled", "disabled"), ("disabled", "disabled")):
            profiles.transition(previous, candidate)
        for previous, candidate in (("base", "enabled"), ("disabled", "base"), ("enabled", "base")):
            with self.subTest(previous=previous, candidate=candidate), self.assertRaises(ValueError):
                profiles.transition(previous, candidate)

    @unittest.skipIf(os.name == "nt", "Linux private recovery/fsync contract")
    def test_first_tombstone_recovery_stays_protected_and_enabled_restore_is_strict(self):
        for previous_profile in ("base", "enabled"):
            with self.subTest(previous=previous_profile), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                root.chmod(0o700)
                for name in ("releases", "attempts", "incoming"):
                    (root / name).mkdir(mode=0o700)
                gateway = release.Gateway(root)
                identity = "b" * 40 + "-1-1"
                staged = root / "releases" / identity
                old = root / "releases" / ("a" * 40 + "-0-0")
                for directory in (staged, old):
                    directory.mkdir(mode=0o700)
                (staged / profiles.VHOST).parent.mkdir(parents=True)
                (staged / profiles.VHOST).write_bytes(b"synthetic-disabled-vhost")
                release.atomic(staged / profiles.MARKER, profiles.descriptor("disabled", b"synthetic-disabled-vhost"))
                image = "nginx@sha256:" + "c" * 64
                candidate = {"services": {"proxy": {"image": image, "volumes": [{"target": "/etc/nginx/conf.d",
                    "source": str(staged / "nginx/vhosts")}]}}, "networks": {}}
                previous_model = {"services": {"proxy": {"image": image, "volumes": []}},
                                  "networks": {"ynab_route": {}} if previous_profile == "enabled" else {}}
                release.atomic(staged / "model.json", candidate)
                release.atomic(old / "model.json", previous_model)
                previous = {"directory": str(old), "source": "a" * 40, "actions_run": "operator", "recovery": None,
                            "profile": previous_profile, "configuration": release.config_identity(previous_model)}
                journal = {"id": identity, "source": "b" * 40, "actions_run": "operator", "previous": previous,
                           "profile": "disabled", "configuration": release.config_identity(candidate),
                           "invariants": {"apps": "same"}, "certs": "/synthetic/certs", "certificates": "same",
                           "ynab_state": {"network": "same", "apps": {}} if previous_profile == "enabled" else None}
                (root / "attempts" / identity).mkdir(mode=0o700)
                release.atomic(root / "pending.json", journal)
                with patch.object(gateway, "syntax"), patch.object(gateway, "compose") as compose, \
                     patch.object(release, "profile_invariants", return_value={"apps": "same"}), \
                     patch.object(release, "ynab_identity", return_value=journal["ynab_state"]), \
                     patch.object(release, "certificate_identity", return_value="same"), patch.object(release, "healthy"), \
                     patch.object(release, "route_health") as health, patch.object(release, "runtime", return_value={"Id": "recovered"}):
                    result = gateway.restore(journal, None)
                if previous_profile == "base":
                    self.assertEqual(compose.call_args.args[0], staged)
                    self.assertEqual(result["outcome"], "protected")
                    self.assertEqual(release.read(root / "current.json")["profile"], "disabled")
                    health.assert_called_once_with("disabled", strict=False, ca=None)
                else:
                    self.assertEqual(compose.call_args.args[0], old)
                    health.assert_called_once_with("enabled", strict=True, ca=None)
                self.assertFalse((root / "pending.json").exists())

    def test_actual_git_archives_flatten_only_selected_vhost_and_keep_four_mounts(self):
        source = transport.run(["git", "rev-parse", "HEAD"]).strip()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for profile in sorted(profiles.PROFILES):
                archive = root / (profile + ".tar")
                transport.source_archive(source, archive, profile)
                directory = root / profile
                directory.mkdir()
                release.unpack(archive, directory)
                self.assertEqual(profiles.read(directory), profile)
                self.assertFalse((directory / "nginx/optional").exists())
                self.assertEqual((directory / "nginx/vhosts/00-notoli.conf").read_bytes(),
                    (Path(__file__).resolve().parents[1] / "nginx/vhosts/00-notoli.conf").read_bytes().replace(b"\r\n", b"\n"))
                env = dict(os.environ, INGRESS_CERTS_DIR="/synthetic/certs")
                model = json.loads(subprocess.check_output(["docker", "compose", "-f", str(directory / "compose.yml"),
                    "config", "--format", "json"], env=env, text=True))
                profiles.apply(model, profile)
                release.validate_model(model, "/synthetic/certs")
                self.assertEqual(len(model["services"]["proxy"]["volumes"]), 4)
                self.assertEqual(profiles.model_profile(model), profile)
                self.assertEqual("ynab_route" in model["networks"], profile == "enabled")

    def test_marker_rejects_missing_or_modified_route_and_malformed_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / profiles.VHOST).parent.mkdir(parents=True)
            route = root / profiles.VHOST
            marker = root / profiles.MARKER
            route.write_bytes(b"fixture-vhost")
            with self.assertRaises(ValueError):
                profiles.read(root)
            marker.write_text(json.dumps(profiles.descriptor("disabled", route.read_bytes())))
            self.assertEqual(profiles.read(root), "disabled")
            route.write_text("changed")
            with self.assertRaises(ValueError):
                profiles.read(root)
            for record in ([], {"version": 1, "profile": [], "vhost_sha256": None}):
                marker.write_text(json.dumps(record))
                with self.assertRaises(ValueError):
                    profiles.read(root)

    def test_enabled_host_policy_is_explicit_and_preserves_notoli_trust(self):
        objects = {}
        for name, (internal, subnet, apps) in release.check_host.NETWORKS.items():
            objects[("network", name)] = {"Internal": internal, "IPAM": {"Config": [{"Subnet": subnet}]},
                "Containers": {app: {"Name": app, "IPv4Address": "172.30.88.3/29"} for app in apps}}
            objects[("network", name)]["Containers"]["proxy"] = {"Name": "host-ingress-proxy", "IPv4Address": "172.30.88.2/29"}
        for name in ("notoli-backend", "macromapper-backend"):
            objects[("container", name)] = {"Config": {"Env": ["DJANGO_TRUSTED_PROXY_IPS=172.30.88.2"]},
                                           "HostConfig": {"PortBindings": {}}}
        objects[("container", "host-ingress-proxy")] = {"State": {"Running": True}, "NetworkSettings": {"Networks": {
            **{name: {} for name in release.check_host.NETWORKS}, "ynab_mcp_private": {"IPAddress": "172.30.89.2"}}}}
        objects[("network", "ynab_mcp_private")] = {"Internal": True, "Driver": "bridge", "EnableIPv6": False,
            "IPAM": {"Config": [{"Subnet": "172.30.89.0/29"}]}, "Containers": {"proxy": {
                "Name": "host-ingress-proxy", "IPv4Address": "172.30.89.2/29"}}}
        with patch.object(release.check_host, "inspect", side_effect=lambda kind, name: copy.deepcopy(objects[(kind, name)])), patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaises(ValueError):
                release.check_host.verify("host")
            release.check_host.verify("host", ynab_enabled=True)
            objects[("container", "notoli-backend")]["Config"]["Env"] = ["DJANGO_TRUSTED_PROXY_IPS=172.30.89.2"]
            with self.assertRaises(ValueError):
                release.check_host.verify("host", ynab_enabled=True)

    def test_activation_requires_real_challenge_metadata_and_private_cache_policy(self):
        class Response:
            def __init__(self, status, body=b"{}", headers=None):
                self.status, self.body = status, body
                self.headers = headers or {"Cache-Control": "private, no-store", "WWW-Authenticate":
                    'Bearer resource_metadata="https://ynab.judeandrewalaba.com/.well-known/oauth-protected-resource/mcp"'}
            def read(self, limit):
                return self.body[:limit]
            def getheader(self, name, default=None):
                return self.headers.get(name, default)
        metadata = json.dumps({"resource": "https://ynab.judeandrewalaba.com/mcp"}).encode()
        with patch.object(release.http.client, "HTTPSConnection") as connection:
            connection.return_value.getresponse.side_effect = [Response(401), Response(200, metadata)] * 2
            release.ynab_health_once("enabled", True, None)
            self.assertEqual(connection.call_count, 4)
            connection.return_value.getresponse.side_effect = [Response(502)]
            release.ynab_health_once("enabled", False, None)
            connection.return_value.getresponse.side_effect = [Response(410)]
            release.ynab_health_once("disabled", False, None)
            for response in (Response(302), Response(200), Response(401, headers={"Cache-Control": "public"})):
                connection.return_value.getresponse.side_effect = [response]
                with self.assertRaises(release.ReleaseError):
                    release.ynab_health_once("enabled", True, None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
