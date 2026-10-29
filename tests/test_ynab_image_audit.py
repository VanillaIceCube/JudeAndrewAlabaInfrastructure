"""Artifact gate regressions: no Docker, credentials or live metadata needed."""
import copy
from datetime import datetime, timezone
import importlib.util
import io
import json
import tarfile
import tempfile
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("ynab_image_audit", Path(__file__).resolve().parents[1] / "scripts/check_ynab_image_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
NOW = datetime(2026, 10, 29, 18, tzinfo=timezone.utc)
IMAGE = "sha256:" + "a" * 64


def fixture():
    names = ["libc6", "squid"] + ["fixture-package-" + str(n) for n in range(20)]
    return {"SchemaVersion": 2, "Trivy": {"Version": audit.VERSION},
            "CreatedAt": NOW.isoformat(), "ArtifactType": "container_image",
            "Metadata": {"ImageID": IMAGE, "ImageConfig": {"architecture": "amd64"},
                         "OS": {"Family": "ubuntu", "Name": "24.04"}},
            "Results": [{"Class": "os-pkgs", "Type": "ubuntu", "Packages": [
                {"ID": name + "@1.0", "Name": name, "Version": "1.0"} for name in names]},
                {"Class": "license", "Licenses": [{"PkgName": "squid", "Name": "GPL-2.0-or-later", "Severity": "HIGH"}]}]}


def expected():
    return {"os": {(p["Name"], p["Version"]) for p in fixture()["Results"][0]["Packages"]},
            "python": {("fastmcp-slim", "4.1.4")}, "node": {("fixture-node", "1.0")}}


class ImageAuditTests(unittest.TestCase):
    def test_debian_identity_preserves_epoch_and_full_revision(self):
        report = fixture()
        report["Results"][0]["Packages"][0].update(ID="libc6@1:2.39-0ubuntu8.6", Version="2.39")
        records = expected()
        records["os"].remove(("libc6", "1.0"))
        records["os"].add(("libc6", "1:2.39-0ubuntu8.6"))
        audit.validate(report, IMAGE, "egress", records, NOW)

    def test_partial_inventory_cannot_pass_with_twenty_os_packages(self):
        report = fixture()
        report["Results"][0]["Packages"].pop()
        with self.assertRaisesRegex(audit.AuditError, "coverage differs"):
            audit.validate(report, IMAGE, "egress", expected(), NOW)

    def test_native_records_are_read_without_extracting_or_running_image_code(self):
        records = {"var/lib/dpkg/status": "\n\n".join(
            "Package: " + name + "\nVersion: " + version + "\nStatus: install ok installed\n"
            for name, version in expected()["os"]),
            "app/node_modules/.package-lock.json": json.dumps({"packages": {
                "": {"name": "fixture-root", "version": "1.0"},
                "node_modules/fixture-node": {"version": "1.0"}}}),
            "opt/gateway-deps/fastmcp_slim-4.1.4.dist-info/METADATA": "Name: fastmcp-slim\nVersion: 4.1.4\n"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "filesystem.tar"
            with tarfile.open(path, "w") as archive:
                for name, text in records.items():
                    content = text.encode()
                    member = tarfile.TarInfo(name)
                    member.size = len(content)
                    archive.addfile(member, io.BytesIO(content))
            self.assertEqual(audit.inventory(path, "gateway"), expected())
            self.assertEqual(list(Path(directory).iterdir()), [path])
            with tarfile.open(path, "w"):
                pass
            with self.assertRaisesRegex(audit.AuditError, "native OS"):
                audit.inventory(path, "egress")

    def test_complete_inventory_does_not_grant_production_approval(self):
        report = fixture()
        report["Results"][1]["Licenses"].append({"FilePath": "/fixture/LICENSE", "Name": "MIT"})
        result = audit.validate(report, IMAGE, "egress", expected(), NOW)
        self.assertFalse(result["production_approved"])
        self.assertEqual(result["license_entries"], 2)

    def test_high_critical_unknown_and_secrets_block_without_echoing_matches(self):
        for severity in ("HIGH", "CRITICAL", "UNKNOWN"):
            report = fixture()
            report["Results"][0]["Vulnerabilities"] = [{"Severity": severity, "VulnerabilityID": "CVE-fixture"}]
            with self.subTest(severity=severity), self.assertRaises(audit.AuditError):
                audit.validate(report, IMAGE, "egress", expected(), NOW)
        report = fixture()
        report["Results"][0]["Secrets"] = [{"Match": "private-sentinel"}]
        with self.assertRaises(audit.AuditError) as error:
            audit.validate(report, IMAGE, "egress", expected(), NOW)
        self.assertNotIn("private-sentinel", str(error.exception))

    def test_zero_os_inventory_is_not_a_clean_scan(self):
        report = fixture()
        report["Results"][0]["Packages"] = []
        with self.assertRaisesRegex(audit.AuditError, "OS package inventory"):
            audit.validate(report, IMAGE, "egress", expected(), NOW)

    def test_missing_runtime_and_license_inventory_block(self):
        for change in (lambda r: r["Results"].pop(),
                       lambda r: r["Results"][0]["Packages"].pop(1)):
            report = fixture()
            change(report)
            with self.assertRaises(audit.AuditError):
                audit.validate(report, IMAGE, "egress", expected(), NOW)
        with self.assertRaisesRegex(audit.AuditError, "Python/Node"):
            audit.validate(fixture(), IMAGE, "gateway", expected(), NOW)
        report = fixture()
        report["Results"].append({"Class": "lang-pkgs", "Type": "python-pkg", "Packages": [
            {"Name": "fastmcp-slim", "Version": "4.1.4"}]})
        with self.assertRaisesRegex(audit.AuditError, "Python/Node"):
            audit.validate(report, IMAGE, "gateway", expected(), NOW)
        report["Results"].append({"Class": "lang-pkgs", "Type": "node-pkg", "Packages": [
            {"Name": "fixture-node", "Version": "1.0"}]})
        audit.validate(report, IMAGE, "gateway", expected(), NOW)

    def test_wrong_identity_version_schema_age_architecture_and_os_fail(self):
        baseline = fixture()
        variants = []
        for key, value in (("SchemaVersion", 1), ("ArtifactType", "filesystem"),
                           ("CreatedAt", "2020-01-01T00:00:00Z"), ("CreatedAt", "2027-01-01T00:00:00Z"),
                           ("Trivy", {"Version": "latest"}), ("Results", [])):
            report = copy.deepcopy(baseline)
            report[key] = value
            variants.append(report)
        for key, value in (("ImageID", "sha256:" + "b" * 64),
                           ("ImageConfig", {"architecture": "arm64"}),
                           ("OS", {"Family": "unknown"}), ("OS", {"Family": "ubuntu", "EOSL": True})):
            report = copy.deepcopy(baseline)
            report["Metadata"][key] = value
            variants.append(report)
        for report in variants:
            with self.subTest(report=report), self.assertRaises(audit.AuditError):
                audit.validate(report, IMAGE, "egress", expected(), NOW)


if __name__ == "__main__":
    unittest.main(verbosity=2)
