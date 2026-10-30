"""Optional gateway profile packaging, topology, health and transition policy."""
import copy
import io
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

    def test_profiles_cannot_first_expose_a_route_during_initial_tombstone_recovery(self):
        profiles.transition_pair("base", "disabled", "base", "disabled")
        profiles.transition_pair("enabled", "enabled", "base", "disabled")
        profiles.transition_pair("disabled", "enabled", "enabled", "enabled")
        for values in (("disabled", "enabled", "base", "disabled"),
                       ("base", "disabled", "disabled", "enabled"),
                       ("base", "base", "base", "enabled"),
                       ("disabled", "disabled", "disabled", "base")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                profiles.transition_pair(*values)

    def test_auth_marker_model_and_network_are_independent_of_ynab(self):
        model = {"services": {"proxy": {"networks": {}, "volumes": []}}, "networks": {}}
        profiles.apply(model, "enabled", auth=True)
        self.assertEqual(profiles.model_profile(model, auth=True), "enabled")
        self.assertEqual(profiles.model_profile(model), "base")
        self.assertEqual(model["networks"], {"mcp_auth_route": {"name": "mcp_auth_private", "external": True}})
        self.assertEqual(model["services"]["proxy"]["networks"], {"mcp_auth_route": {"ipv4_address": "172.30.92.2"}})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vhost = root / profiles.AUTH_VHOST
            vhost.parent.mkdir(parents=True)
            vhost.write_bytes(b"auth-disabled")
            with self.assertRaises(ValueError):
                profiles.read(root, auth=True)
            (root / profiles.AUTH_MARKER).write_text(json.dumps(profiles.descriptor("disabled", vhost.read_bytes())))
            self.assertEqual(profiles.read(root, auth=True), "disabled")
            self.assertEqual(profiles.read(root), "base")
            vhost.write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                profiles.read(root, auth=True)

    def test_unknown_auth_profile_fails_before_source_or_credentials(self):
        with self.assertRaises(ValueError):
            profiles.selected({"MCP_AUTH_ROUTE_PROFILE": "unknown"}, auth=True)

    def test_optional_route_ipam_accepts_only_absent_or_empty_range(self):
        policy = release.check_host
        valid = {"Subnet": "172.30.92.0/29", "Gateway": "172.30.92.1"}
        self.assertTrue(policy.exact_ipam([valid], valid["Subnet"], valid["Gateway"]))
        self.assertTrue(policy.exact_ipam([{**valid, "IPRange": ""}], valid["Subnet"], valid["Gateway"]))
        for record in ({**valid, "IPRange": None}, {**valid, "IPRange": "172.30.92.0/30"},
                       {**valid, "AuxiliaryAddresses": {}}, {**valid, "Gateway": "172.30.92.4"}):
            self.assertFalse(policy.exact_ipam([record], valid["Subnet"], valid["Gateway"]))

    def test_auth_route_enforces_fixed_members_and_exact_stopped_project_identity(self):
        route = {"Id": "auth-network-id", "Internal": True, "Driver": "bridge", "EnableIPv6": False,
                 "IPAM": {"Config": [{"Subnet": "172.30.92.0/29", "Gateway": "172.30.92.1", "IPRange": ""}]},
                 "Containers": {"proxy": {"Name": "host-ingress-proxy", "IPv4Address": "172.30.92.2/29"},
                                "app": {"Name": "mcp-auth-server", "IPv4Address": "172.30.92.3/29"}}}
        stopped = {"State": {"Status": "exited", "Running": False},
                   "Config": {"Labels": {"com.docker.compose.project": "mcp-auth", "com.docker.compose.service": "authorization"}},
                   "NetworkSettings": {"Networks": {"mcp_auth_private": {"NetworkID": "auth-network-id", "IPAddress": ""}}}}
        attached = copy.deepcopy(stopped)
        attached["NetworkSettings"]["Networks"]["mcp_auth_private"]["IPAddress"] = "172.30.92.3"
        attached["NetworkSettings"]["Networks"]["mcp_auth_private"]["Aliases"] = ["mcp-auth"]
        with patch.object(release.check_host, "inspect", side_effect=lambda kind, name: route if kind == "network" else
                          attached if "app" in route["Containers"] else stopped):
            release.check_host.auth_route()
            attached["Config"]["Labels"]["com.docker.compose.project"] = "foreign"
            with self.assertRaises(ValueError):
                release.check_host.auth_route()
            attached["Config"]["Labels"]["com.docker.compose.project"] = "mcp-auth"
            attached["NetworkSettings"]["Networks"]["mcp_auth_private"]["Aliases"] = []
            with self.assertRaises(ValueError):
                release.check_host.auth_route()
            attached["NetworkSettings"]["Networks"]["mcp_auth_private"]["Aliases"] = ["mcp-auth"]
            route["Containers"]["app"]["IPv4Address"] = "172.30.92.4/29"
            with self.assertRaises(ValueError):
                release.check_host.auth_route()
            route["Containers"].pop("app")
            with self.assertRaises(ValueError):
                release.check_host.auth_route()
            release.check_host.auth_route(allow_stopped_gateway=True)
            stopped["Config"]["Labels"]["com.docker.compose.project"] = "foreign"
            with self.assertRaises(ValueError):
                release.check_host.auth_route(allow_stopped_gateway=True)

    @unittest.skipIf(os.name == "nt", "Linux private recovery/fsync contract")
    def test_first_tombstone_recovery_stays_protected_and_enabled_restore_is_strict(self):
        for previous_profile, auth in (("base", False), ("enabled", False), ("base", True), ("enabled", True)):
            with self.subTest(previous=previous_profile, auth=auth), tempfile.TemporaryDirectory() as temporary:
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
                vhost, marker = (profiles.AUTH_VHOST, profiles.AUTH_MARKER) if auth else (profiles.VHOST, profiles.MARKER)
                (staged / vhost).parent.mkdir(parents=True)
                (staged / vhost).write_bytes(b"synthetic-disabled-vhost")
                release.atomic(staged / marker, profiles.descriptor("disabled", b"synthetic-disabled-vhost"))
                image = "nginx@sha256:" + "c" * 64
                candidate = {"services": {"proxy": {"image": image, "volumes": [{"target": "/etc/nginx/conf.d",
                    "source": str(staged / "nginx/vhosts")}]}}, "networks": {}}
                previous_model = {"services": {"proxy": {"image": image, "volumes": []}},
                                  "networks": {"mcp_auth_route" if auth else "ynab_route": {}} if previous_profile == "enabled" else {}}
                release.atomic(staged / "model.json", candidate)
                release.atomic(old / "model.json", previous_model)
                previous = {"directory": str(old), "source": "a" * 40, "actions_run": "operator", "recovery": None,
                            "profile": "base" if auth else previous_profile,
                            "auth_profile": previous_profile if auth else "base", "configuration": release.config_identity(previous_model)}
                journal = {"id": identity, "source": "b" * 40, "actions_run": "operator", "previous": previous,
                           "profile": "base" if auth else "disabled", "auth_profile": "disabled" if auth else "base",
                           "configuration": release.config_identity(candidate),
                           "invariants": {"apps": "same"}, "certs": "/synthetic/certs", "certificates": "same",
                           "ynab_state": {"network": "same", "apps": {}} if previous_profile == "enabled" and not auth else None,
                           "auth_state": {"network": "same", "app": []} if previous_profile == "enabled" and auth else None}
                (root / "attempts" / identity).mkdir(mode=0o700)
                release.atomic(root / "pending.json", journal)
                with patch.object(gateway, "syntax"), patch.object(gateway, "compose") as compose, \
                     patch.object(release, "profile_invariants", return_value={"apps": "same"}), \
                     patch.object(release, "ynab_identity", return_value=journal["ynab_state"]), \
                     patch.object(release, "auth_identity", return_value=journal["auth_state"]), \
                     patch.object(release, "certificate_identity", return_value="same"), patch.object(release, "healthy"), \
                     patch.object(release, "macro_mcp_enabled", return_value=False), \
                     patch.object(release, "auth_route_health" if auth else "route_health") as health, \
                     patch.object(release, "runtime", return_value={"Id": "recovered"}):
                    if auth and previous_profile == "enabled":
                        with patch.object(release, "auth_identity", side_effect=release.ReleaseError("pending authorization release")), \
                             self.assertRaises(release.ReleaseError):
                            gateway.restore(journal, None)
                        compose.assert_not_called()
                    result = gateway.restore(journal, None)
                if previous_profile == "base":
                    self.assertEqual(compose.call_args.args[0], staged)
                    self.assertEqual(result["outcome"], "protected")
                    self.assertEqual(release.read(root / "current.json")["auth_profile" if auth else "profile"], "disabled")
                    health.assert_called_once_with("disabled", strict=False, ca=None)
                else:
                    self.assertEqual(compose.call_args.args[0], old)
                    health.assert_called_once_with("enabled", strict=True, ca=None)
                self.assertFalse((root / "pending.json").exists())

    def test_both_route_profiles_archive_exact_committed_blobs_into_existing_mounts(self):
        # A disposable source repository includes the currently reviewed bytes,
        # so this exercises real immutable Git blobs before the feature commit.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            repository = Path(__file__).resolve().parents[1]
            shutil.copyfile(repository / "compose.yml", source / "compose.yml")
            shutil.copytree(repository / "nginx", source / "nginx")
            (source / "scripts").mkdir()
            for name in ("gateway_release.py", "gateway_profile.py", "check_host.py"):
                shutil.copyfile(repository / "scripts" / name, source / "scripts" / name)
            hooks = root / "empty-hooks"
            hooks.mkdir()
            environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
            def source_git(args):
                return subprocess.check_output([args[0], "-C", source, *args[1:]], text=True, env=environment)
            def git(*args):
                return source_git(["git", "-c", "core.hooksPath=" + str(hooks),
                    "-c", "commit.gpgsign=false", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args])
            git("init", "--quiet")
            git("add", "compose.yml", "nginx", "scripts")
            git("commit", "--quiet", "-m", "Disposable reviewed profile source")
            commit = git("rev-parse", "HEAD").strip()
            for profile in sorted(profiles.PROFILES):
                for auth_profile in sorted(profiles.PROFILES):
                    name = profile + "-" + auth_profile
                    archive, directory = root / (name + ".tar"), root / name
                    directory.mkdir()
                    with patch.object(transport, "run", side_effect=source_git):
                        transport.source_archive(commit, archive, profile, auth_profile)
                    release.unpack(archive, directory)
                    self.assertFalse((directory / "nginx/optional").exists())
                    self.assertEqual((directory / "nginx/vhosts/00-notoli.conf").read_bytes(),
                        (repository / "nginx/vhosts/00-notoli.conf").read_bytes().replace(b"\r\n", b"\n"))
                    self.assertEqual(profiles.read(directory), profile)
                    self.assertEqual(profiles.read(directory, auth=True), auth_profile)
                    model = json.loads(subprocess.check_output(["docker", "compose", "-f", str(directory / "compose.yml"),
                        "config", "--format", "json"], env=dict(os.environ, INGRESS_CERTS_DIR="/synthetic/certs"), text=True))
                    profiles.apply(model, profile)
                    profiles.apply(model, auth_profile, auth=True)
                    release.validate_model(model, "/synthetic/certs")
                    self.assertEqual(len(model["services"]["proxy"]["volumes"]), 4)
                    self.assertEqual(profiles.model_profile(model), profile)
                    self.assertEqual(profiles.model_profile(model, auth=True), auth_profile)
            legacy = copy.deepcopy(model)
            legacy["services"]["proxy"]["networks"]["macromapper"] = None
            self.assertFalse(release.macro_route_contract(legacy))
            self.assertTrue(release.macro_route_contract(model))
            with self.assertRaises(release.ReleaseError):
                release.validate_model(legacy, "/synthetic/certs")
            legacy["services"]["proxy"]["networks"]["macromapper"] = {"ipv4_address": "172.20.0.4"}
            with self.assertRaises(release.ReleaseError):
                release.macro_route_contract(legacy)

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
            objects[("network", name)]["Containers"]["proxy"] = {"Name": "host-ingress-proxy",
                "IPv4Address": "172.20.0.3/16" if name == "macromapper-ingress" else "172.30.88.2/29"}
        for name in ("notoli-backend", "macromapper-backend"):
            objects[("container", name)] = {"Config": {"Env": ["DJANGO_TRUSTED_PROXY_IPS=172.30.88.2"]},
                                           "HostConfig": {"PortBindings": {}}}
        objects[("container", "host-ingress-proxy")] = {"State": {"Running": True}, "NetworkSettings": {"Networks": {
            **{name: {} for name in release.check_host.NETWORKS}, "ynab_mcp_private": {"IPAddress": "172.30.89.2"}}}}
        objects[("network", "ynab_mcp_private")] = {"Id": "route-fixture-id", "Internal": True, "Driver": "bridge", "EnableIPv6": False,
            "IPAM": {"Config": [{"Subnet": "172.30.89.0/29", "Gateway": "172.30.89.1"}]}, "Containers": {"proxy": {
                "Name": "host-ingress-proxy", "IPv4Address": "172.30.89.2/29"}, "app": {
                "Name": "ynab-mcp-gateway-1", "IPv4Address": "172.30.89.3/29"}}}
        with patch.object(release.check_host, "inspect", side_effect=lambda kind, name: copy.deepcopy(objects[(kind, name)])), patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaises(ValueError):
                release.check_host.verify("host")
            release.check_host.verify("host", ynab_enabled=True)
            macro_proxy = objects[("network", "macromapper-ingress")]["Containers"]["proxy"]
            macro_proxy["IPv4Address"] = "172.20.0.4/16"
            with self.assertRaises(ValueError):
                release.check_host.verify("host", ynab_enabled=True)
            macro_proxy["IPv4Address"] = "172.20.0.3/16"
            ipam = objects[("network", "ynab_mcp_private")]["IPAM"]
            valid = copy.deepcopy(ipam["Config"])
            for invalid in ([{"Subnet": "172.30.89.0/29", "Gateway": "172.30.89.4"}],
                            [{"Subnet": "172.30.89.0/29"}],
                            [{**valid[0], "AuxiliaryAddresses": {"unexpected": "172.30.89.5"}}]):
                ipam["Config"] = invalid
                with self.assertRaises(ValueError):
                    release.check_host.verify("host", ynab_enabled=True)
            ipam["Config"] = valid
            route = objects[("network", "ynab_mcp_private")]
            app_member = route["Containers"].pop("app")
            with self.assertRaisesRegex(ValueError, "required YNAB"):
                release.check_host.verify("host", ynab_enabled=True)
            app = {"State": {"Running": False, "Status": "exited", "Dead": False, "Restarting": False}, "Config": {"Labels": {
                "com.docker.compose.project": "ynab-mcp", "com.docker.compose.service": "gateway"}},
                "NetworkSettings": {"Networks": {"ynab_mcp_private": {"IPAddress": "", "NetworkID": route["Id"]}}}}
            objects[("container", "ynab-mcp-gateway-1")] = app
            release.check_host.ynab_route(allow_stopped_gateway=True)
            for field, value in (("State", {"Running": True}), ("Config", {"Labels": {}}),
                                 ("State", {"Running": False, "Status": "created"}),
                                 ("State", {"Running": False, "Status": "exited", "Dead": True}),
                                 ("State", {"Running": False, "Status": "restarting"}),
                                 ("NetworkSettings", {"Networks": {"ynab_mcp_private": {"IPAddress": "", "NetworkID": "stale"}}}),
                                 ("NetworkSettings", {"Networks": {}})):
                with patch.dict(app, {field: value}), self.assertRaises(ValueError):
                    release.check_host.ynab_route(allow_stopped_gateway=True)
            route["Containers"]["app"] = app_member
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
            connection.return_value.getresponse.side_effect = [Response(410)] * 2
            release.ynab_health_once("disabled", False, None)
            for response in (Response(302), Response(200), Response(401, headers={"Cache-Control": "public"})):
                connection.return_value.getresponse.side_effect = [response]
                with self.assertRaises(release.ReleaseError):
                    release.ynab_health_once("enabled", True, None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
