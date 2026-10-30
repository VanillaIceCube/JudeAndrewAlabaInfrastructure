"""Authorization artifacts use fresh scanner evidence, never saved approvals."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import preflight_mcp_auth_release as gate
import preflight_ynab_release as shared

REFERENCE = shared.AUTH_REPOSITORY + "@sha256:" + "a" * 64
IDENTITY = "sha256:" + "b" * 64


class AuthArtifactPreflightTests(unittest.TestCase):
    def test_role_specific_identity_rejects_other_repository_tag_and_architecture(self):
        for reference in (shared.PREFIX + "gateway@sha256:" + "a" * 64,
                          shared.AUTH_REPOSITORY + ":latest"):
            with self.assertRaises(shared.AuditError):
                shared.inspect(reference, "authorization")
        for architecture, digests in (("arm64", [REFERENCE]), ("amd64", [])):
            with patch.object(shared, "docker", return_value=json.dumps([{
                "Id": IDENTITY, "RepoDigests": digests, "Os": "linux", "Architecture": architecture}]).encode()):
                with self.assertRaises(shared.AuditError):
                    shared.inspect(REFERENCE, "authorization")

    def test_every_invocation_requires_fresh_exact_authorization_scan(self):
        scanner, cache = Path("scanner"), Path("cache")
        with patch.object(gate.os, "name", "posix"), patch.object(gate, "inspect", return_value=IDENTITY) as identity, \
                patch.object(gate, "audit_local") as scan:
            for _ in range(2):
                self.assertEqual(gate.preflight(REFERENCE, scanner, cache), {"reference": REFERENCE, "image_id": IDENTITY})
            self.assertEqual(identity.call_count, 2)
            self.assertEqual(scan.call_count, 2)
            scan.assert_called_with(IDENTITY, "authorization", scanner, cache)
            scan.side_effect = shared.AuditError("New advisory blocks release")
            with self.assertRaises(shared.AuditError):
                gate.preflight(REFERENCE, scanner, cache)


if __name__ == "__main__":
    unittest.main()
