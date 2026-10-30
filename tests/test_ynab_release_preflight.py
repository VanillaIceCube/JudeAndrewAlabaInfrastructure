"""Both exact image roles must pass new scans; no saved approvals or mutations."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import preflight_ynab_release as gate

IMAGES = {role: gate.PREFIX + role + "@sha256:" + digit * 64
          for role, digit in (("gateway", "a"), ("egress", "b"))}
IDS = {"gateway": "sha256:" + "c" * 64, "egress": "sha256:" + "d" * 64}


class ReleaseArtifactPreflightTests(unittest.TestCase):
    def test_malformed_export_keeps_private_details_out_of_cli_diagnostics(self):
        with patch.object(gate, "preflight", side_effect=gate.tarfile.TarError("private-sentinel")):
            with self.assertRaises(SystemExit) as error:
                gate.main(["--gateway", IMAGES["gateway"], "--egress", IMAGES["egress"],
                           "--scanner", "scanner", "--cache", "cache"])
        self.assertNotIn("private-sentinel", str(error.exception))
        self.assertIn("blocked", str(error.exception))

    def test_missing_or_single_image_never_reaches_scanner(self):
        for images in ({}, {"gateway": IMAGES["gateway"]}, {"egress": IMAGES["egress"]}):
            with patch.object(gate, "audit") as scanner, self.assertRaises(gate.AuditError):
                gate.preflight(images, Path("scanner"), Path("cache"))
            scanner.assert_not_called()

    def test_role_mutable_tag_and_registry_digest_mismatch_block(self):
        for reference in (IMAGES["egress"], "ghcr.io/example/gateway:latest"):
            with self.assertRaises(gate.AuditError):
                gate.inspect(reference, "gateway")
        with patch.object(gate, "docker", return_value=json.dumps([{
                "RepoDigests": [], "Id": IDS["gateway"], "Os": "linux", "Architecture": "amd64"}]).encode()):
            with self.assertRaises(gate.AuditError):
                gate.inspect(IMAGES["gateway"], "gateway")

    def run_gate(self, failures=None):
        commands = []
        current = None
        def docker(*arguments):
            nonlocal current
            commands.append(arguments)
            if arguments[0] == "create":
                current = arguments[-1]
            if arguments[:2] == ("container", "inspect"):
                return json.dumps([{"Image": current, "State": {"Status": "created"}}]).encode()
            return b""
        with patch.object(gate.os, "name", "posix"), patch.object(gate, "inspect", side_effect=lambda ref, role: IDS[role]), \
             patch.object(gate, "docker", side_effect=docker), patch.object(gate, "audit", side_effect=failures) as audit:
            result = gate.preflight(IMAGES, Path("scanner"), Path("cache"))
        return result, commands, audit.call_args_list

    @unittest.skipUnless(gate.os.name == "posix", "Linux filesystem/export orchestration fixture")
    def test_both_roles_are_scanned_and_only_never_started_fixtures_are_removed(self):
        result, commands, scans = self.run_gate()
        self.assertEqual(set(result), {"gateway", "egress"})
        self.assertEqual([call.args[3] for call in scans], ["gateway", "egress"])
        self.assertEqual([call.args[2] for call in scans], [IDS["gateway"], IDS["egress"]])
        self.assertFalse(any(command[0] in {"start", "run", "pull", "push", "network", "compose"} for command in commands))
        self.assertEqual(sum(command[:3] == ("container", "rm", "-v") for command in commands), 2)

    @unittest.skipUnless(gate.os.name == "posix", "Linux filesystem/export orchestration fixture")
    def test_stale_mismatched_or_failed_second_scan_cannot_return_a_release_result(self):
        for reason in ("Stale/future scan report", "Image identity mismatch", "Missing package coverage"):
            with self.subTest(reason=reason), self.assertRaises(gate.AuditError):
                self.run_gate([{}, gate.AuditError(reason)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
