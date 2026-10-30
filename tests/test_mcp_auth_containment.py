"""Database operations require accepted tombstones and verified origin evidence."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import mcp_auth_containment as gate
import mcp_auth_release


class Response:
    def __init__(self, status=410, body=b"contained", cache="no-store"):
        self.status, self.body, self.cache = status, body, cache

    def read(self, limit):
        return self.body[:limit]

    def getheader(self, name, default=None):
        return self.cache if name == "Cache-Control" else default


class ContainmentTests(unittest.TestCase):
    def test_ynab_release_tracks_auth_companions_while_both_routes_are_disabled(self):
        record = {"directory": str(gate.common.ROOT / "releases" / "fixture"), "profile": "disabled",
                  "auth_profile": "disabled", "runtime": {"accepted": True}}
        proxy = {"NetworkSettings": {"Networks": {}},
                 "Mounts": [{"Destination": "/etc/nginx/certs", "Source": "/private/certs"}]}
        with patch.object(gate.common, "inspect", return_value=proxy), patch.object(gate.common, "private"), \
             patch.object(gate.common, "read", side_effect=lambda path: record if path.name == "current.json" else {}), \
             patch.object(gate.common.profiles, "model_profile", return_value="disabled"), \
             patch.object(gate.common, "runtime", return_value=record["runtime"]), \
             patch.object(gate.common, "invariants", side_effect=lambda **kwargs: {"apps": "unchanged"}), \
             patch.object(gate.common, "certificate_identity", return_value="certificate-fingerprint"), \
             patch.object(gate.common, "docker", return_value="auth-container"), \
             patch.object(mcp_auth_release, "runtime", side_effect=[{"Id": "first"}, {"Id": "second"}]):
            before = gate.ynab_release.companions()
            after = gate.ynab_release.companions()
        self.assertEqual(before["authorization"], {"Id": "first"})
        self.assertNotEqual(before, after)

    def test_public_auth_route_requires_the_accepted_service_runtime(self):
        value = {"Id": "accepted-container", "Image": "accepted-image", "Config": {"Labels": {}},
                 "HostConfig": {"ReadonlyRootfs": True}, "Mounts": [], "State": {"StartedAt": "start"}}
        record = {"source": "a" * 40, "disabled": False, "runtime": {
            **{key: value[key] for key in ("Id", "Image", "Config", "HostConfig", "Mounts")}, "started": "start"}}
        with tempfile.TemporaryDirectory() as temporary, patch.object(gate.common, "AUTH_RELEASE_ROOT", Path(temporary)), \
             patch.object(gate.common, "private"), patch.object(gate.common, "read", return_value=record), \
             patch.object(gate.common.check_host, "auth_route", return_value={"Id": "network-id"}), \
             patch.object(gate.common, "docker", return_value="container-id"), \
             patch.object(gate.common, "inspect", return_value=value):
            self.assertEqual(gate.common.auth_identity()["source"], record["source"])
            record["runtime"]["Id"] = "foreign-container"
            with self.assertRaises(gate.common.ReleaseError):
                gate.common.auth_identity()

    @unittest.skipIf(os.name == "nt", "Linux protected quarantine permissions")
    def test_restore_quarantine_blocks_ynab_reexposure_until_deadline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            path = root / "ynab-jwt-quarantine.json"
            path.write_text(json.dumps({"version": 1, "not_before": 1905}))
            path.chmod(0o600)
            with patch.object(gate.common, "AUTH_RELEASE_ROOT", root), patch.object(gate.common.time, "time", return_value=1904):
                with self.assertRaises(gate.common.ReleaseError):
                    gate.common.ynab_exposure_transition("disabled", "enabled")
                gate.common.ynab_exposure_transition("enabled", "disabled")
                gate.common.ynab_exposure_transition("enabled", "enabled")
                with patch.object(gate.common.time, "time", return_value=1905):
                    gate.common.ynab_exposure_transition("disabled", "enabled")
                pending = root / "pending.json"
                pending.write_text("{}")
                with self.assertRaises(gate.common.ReleaseError):
                    gate.common.ynab_reexposure_allowed()
                pending.unlink()
                for bad in ({"version": 1, "not_before": True}, {"version": 1, "not_before": 1900, "override": True}, []):
                    path.write_text(json.dumps(bad))
                    with self.assertRaises(gate.common.ReleaseError):
                        gate.common.ynab_reexposure_allowed()
                path.unlink()
                path.symlink_to(root / "missing")
                with self.assertRaises(gate.common.ReleaseError):
                    gate.common.ynab_reexposure_allowed()

    def test_both_profiles_must_be_accepted_disabled_before_any_probe(self):
        for profiles in (("base", "disabled"), ("disabled", "base"), ("enabled", "disabled"), ("disabled", "enabled")):
            with patch.object(gate, "accepted_gateway", return_value=({}, *profiles)), \
                 patch.object(gate.common, "auth_health_once") as probe, self.assertRaises(gate.common.ReleaseError):
                gate.require_contained()
            probe.assert_not_called()

    def test_missing_operator_ca_cannot_be_replaced_by_system_or_candidate_trust(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(gate.common, "ROOT", Path(temporary)), \
             patch.object(gate, "accepted_gateway", return_value=({}, "disabled", "disabled")), \
             patch.object(gate.common, "auth_health_once") as probe:
            with self.assertRaises(OSError):
                gate.require_contained()
            probe.assert_not_called()

    def test_origin_all_auth_and_ynab_routes_must_return_uncached_410(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ca = root / "origin-ca.pem"
            ca.write_text("synthetic-ca")
            with patch.object(gate.common, "ROOT", root), \
                 patch.object(gate, "accepted_gateway", return_value=({}, "disabled", "disabled")), \
                 patch.object(gate.common.ssl, "create_default_context") as tls, \
                 patch.object(gate.common.http.client, "HTTPSConnection") as connection:
                connection.return_value.getresponse.return_value = Response()
                self.assertTrue(gate.require_contained())
                requests = [call.args[1] for call in connection.return_value.request.call_args_list]
                self.assertEqual(requests, [*gate.common.AUTH_PATHS, "/mcp", "/.well-known/oauth-protected-resource/mcp"])
                self.assertTrue(all(call.kwargs == {"cafile": str(ca)} for call in tls.call_args_list))
                self.assertEqual({call.args[0] for call in connection.call_args_list},
                                 {"auth.judeandrewalaba.com", "ynab.judeandrewalaba.com"})
                for response in (Response(200), Response(302), Response(410, cache="public")):
                    connection.return_value.getresponse.return_value = response
                    with self.assertRaises(gate.common.ReleaseError):
                        gate.require_contained()

    def test_pending_gateway_or_ynab_prevents_accepted_state_reads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("gateway", "ynab"):
                (root / name).mkdir()
            for owner in ("gateway", "ynab"):
                pending = root / owner / "pending.json"
                pending.write_text("{}")
                with patch.object(gate.common, "ROOT", root / "gateway"), \
                     patch.object(gate.ynab_release, "ROOT", root / "ynab"), \
                     patch.object(gate.common.Gateway, "current") as current, self.assertRaises(gate.common.ReleaseError):
                    gate.accepted_gateway()
                current.assert_not_called()
                pending.unlink()

    def test_baseline_includes_accepted_gateway_companions_and_certificate_identity(self):
        record = {"runtime": {"Mounts": [{"Destination": "/etc/nginx/certs", "Source": "/private/certs"}]}}
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(gate.ynab_release, "ROOT", Path(temporary)), \
             patch.object(gate, "accepted_gateway", return_value=(record, "disabled", "disabled")), \
             patch.object(gate.common, "profile_invariants", return_value={"apps": "unchanged", "networks": "ids"}) as invariant, \
             patch.object(gate.common, "certificate_identity", return_value="certificate-fingerprint"), \
             patch.object(gate.ynab_release, "runtime", return_value={}):
            value = gate.baseline()
        self.assertEqual(value, {"gateway": record, "apps": "unchanged", "networks": "ids", "ynab": None,
                                "certificates": "certificate-fingerprint"})
        invariant.assert_called_once_with("disabled", auth_profile="disabled")

    def test_unaccepted_ynab_runtime_is_not_a_tolerated_companion(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(gate.ynab_release, "ROOT", Path(temporary)), \
             patch.object(gate, "accepted_gateway", return_value=({}, "disabled", "disabled")), \
             patch.object(gate.common, "profile_invariants", return_value={}), \
             patch.object(gate.ynab_release, "runtime", return_value={"gateway": "unaccepted"}), \
             self.assertRaises(gate.common.ReleaseError):
            gate.baseline()

    def test_auth_exposure_requires_fixed_issuer_endpoints_pkce_and_no_cache(self):
        issuer = "https://auth.judeandrewalaba.com"
        metadata = {"issuer": issuer, "authorization_endpoint": issuer + "/o/authorize/",
                    "token_endpoint": issuer + "/o/token/", "code_challenge_methods_supported": ["S256"]}
        with patch.object(gate.common.http.client, "HTTPSConnection") as connection:
            connection.return_value.getresponse.return_value = Response(200, json.dumps(metadata).encode())
            gate.common.auth_health_once("enabled", True, None)
            self.assertEqual(connection.call_count, 2)
            for bad in ({**metadata, "issuer": "https://other.example"}, {**metadata, "code_challenge_methods_supported": ["plain"]}):
                connection.return_value.getresponse.return_value = Response(200, json.dumps(bad).encode())
                with self.assertRaises(gate.common.ReleaseError):
                    gate.common.auth_health_once("enabled", True, None)
            connection.return_value.getresponse.return_value = Response(503)
            gate.common.auth_health_once("enabled", False, None)
            with self.assertRaises(gate.common.ReleaseError):
                gate.common.auth_health_once("enabled", True, None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
