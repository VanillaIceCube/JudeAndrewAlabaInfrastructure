"""Bounded, credential-free image audit. This does not authorize publication/deployment.

Run on Linux against a locally exported, credential-free candidate. The caller
binds its expected image ID to the build/registry evidence. Raw findings stay
in a private cache, never stdout or public CI artifacts.
"""
import argparse
from datetime import datetime, timedelta, timezone
from email.parser import Parser
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import uuid

VERSION = "0.76.1"
BINARY_SHA256 = "d1dfca6ae10a1ad4540bb94e64f0510077c47008920a9b554986b39dca573d83"
DIGEST = re.compile(r"sha256:[a-f0-9]{64}")
SEVERITIES = {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}


class AuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AuditError(message)


def timestamp(value):
    require(isinstance(value, str), "Missing audit timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AuditError("Invalid audit timestamp") from error
    require(result.tzinfo is not None, "Audit timestamp needs a timezone")
    return result


def inventory(filesystem, role):
    """Read package records from a never-started container export; extract nothing.

    Missing native package metadata is a blocker, not an invitation to invent it.
    This checks recorded packages; provenance review still owns untracked/copied
    binaries and the Node/Python interpreter base pins.
    """
    expected = {"os": set(), "python": set(), "node": set()}
    records = {}
    total = 0
    with tarfile.open(filesystem, mode="r|*") as archive:
        for count, member in enumerate(archive):
            require(count < 100_000, "Filesystem inventory exceeds entry limit")
            name = member.name.removeprefix("./")
            selected = (name == "var/lib/dpkg/status" or
                        name == "app/node_modules/.package-lock.json" or
                        (name.startswith("opt/gateway-deps/") and name.endswith(".dist-info/METADATA")))
            if not selected:
                continue
            require(member.isfile() and name not in records and 0 < member.size <= 10_000_000,
                    "Unsafe/oversized inventory metadata")
            total += member.size
            require(total <= 30_000_000, "Filesystem inventory exceeds size limit")
            records[name] = archive.extractfile(member).read().decode("utf-8")
    require("var/lib/dpkg/status" in records, "Missing native OS package records")
    for paragraph in records.pop("var/lib/dpkg/status").split("\n\n"):
        package = Parser().parsestr(paragraph.strip())
        if package.get("Status") == "install ok installed":
            require(package.get("Package") and package.get("Version"), "Incomplete OS package record")
            expected["os"].add((package["Package"], package["Version"]))
    require(len(expected["os"]) >= 20, "Missing/thin native OS inventory")
    lock = records.pop("app/node_modules/.package-lock.json", None)
    if role == "gateway":
        require(lock is not None, "Missing installed Node lock inventory")
        packages = json.loads(lock).get("packages")
        require(isinstance(packages, dict) and packages, "Missing installed Node packages")
        for path, package in packages.items():
            # npm's ordinary v2/v3 lock may include the application's root;
            # it is not an installed node_modules dependency. Hidden installed
            # locks generally omit it, but both forms must retain full coverage.
            if path == "":
                require(isinstance(package, dict), "Malformed Node root record")
                continue
            require("node_modules/" in path and isinstance(package, dict) and package.get("version"),
                    "Incomplete installed Node package record")
            expected["node"].add((path.rsplit("node_modules/", 1)[1], package["version"]))
        require(expected["node"], "Missing installed Node dependencies")
        for text in records.values():
            package = Parser().parsestr(text)
            require(package.get("Name") and package.get("Version"), "Incomplete installed Python package record")
            expected["python"].add((re.sub(r"[-_.]+", "-", package["Name"]).lower(), package["Version"]))
        require(any(name == "fastmcp-slim" for name, _ in expected["python"]), "Missing installed gateway Python inventory")
    return expected


def validate(report, image_id, role, expected, now=None):
    """Reject incomplete coverage, secret findings and known HIGH/CRITICAL CVEs.

    License severity is a legal classification, not vulnerability severity.
    Inventory is required; a separate license/provenance review remains mandatory.
    """
    now = now or datetime.now(timezone.utc)
    require(role in {"gateway", "egress"}, "Unsupported image role")
    require(isinstance(report, dict) and report.get("SchemaVersion") == 2,
            "Unsupported scanner report schema")
    require(report.get("Trivy", {}).get("Version") == VERSION, "Scanner version mismatch")
    require(report.get("ArtifactType") == "container_image", "Expected container image report")
    require(DIGEST.fullmatch(image_id) and report.get("Metadata", {}).get("ImageID") == image_id,
            "Image identity mismatch")
    age = now - timestamp(report.get("CreatedAt"))
    require(timedelta(minutes=-5) <= age <= timedelta(hours=24), "Stale/future scan report")
    metadata = report.get("Metadata", {})
    require(metadata.get("ImageConfig", {}).get("architecture") == "amd64", "Unexpected architecture")
    require(metadata.get("OS", {}).get("Family") in {"ubuntu", "debian"}, "Unsupported OS inventory")
    require(not metadata.get("OS", {}).get("EOSL", False), "End-of-life OS")
    results = report.get("Results")
    require(isinstance(results, list) and results, "Missing scanner results")
    packages, licenses, counts, secret_count = set(), set(), dict.fromkeys(SEVERITIES, 0), 0
    observed = {"os": set(), "python": set(), "node": set()}
    for row in results:
        require(isinstance(row, dict), "Malformed scanner result")
        for package in row.get("Packages", []):
            require(isinstance(package, dict) and package.get("Name") and package.get("Version"),
                    "Incomplete package inventory")
            if row.get("Class") == "os-pkgs":
                packages.add(package["Name"])
                # Trivy's Debian ID retains epoch and full revision even when
                # the Version field is split into optional component fields.
                prefix = package["Name"] + "@"
                identifier = package.get("ID")
                require(isinstance(identifier, str) and identifier.startswith(prefix) and
                        len(identifier) > len(prefix), "Incomplete OS package identity")
                version = identifier[len(prefix):]
                observed["os"].add((package["Name"], version))
            elif row.get("Type") == "python-pkg":
                observed["python"].add((re.sub(r"[-_.]+", "-", package["Name"]).lower(), package["Version"]))
            elif row.get("Type") == "node-pkg":
                observed["node"].add((package["Name"], package["Version"]))
        for finding in row.get("Vulnerabilities", []):
            severity = finding.get("Severity")
            require(severity in SEVERITIES and finding.get("VulnerabilityID"), "Incomplete vulnerability finding")
            counts[severity] += 1
        secrets = row.get("Secrets", [])
        require(isinstance(secrets, list), "Malformed secret findings")
        secret_count += len(secrets)
        for license_item in row.get("Licenses", []):
            require(isinstance(license_item, dict) and license_item.get("Name") and
                    (license_item.get("PkgName") or license_item.get("FilePath")),
                    "Incomplete license inventory")
            licenses.add((license_item.get("PkgName") or license_item["FilePath"], license_item["Name"]))
    # A newer Rock candidate reports its OS but zero recognized OS packages.
    # Refuse that blind spot rather than treating zero CVEs as a clean image.
    require(len(packages) >= 20 and "libc6" in packages, "Missing/thin OS package inventory")
    require(expected.get("os") and observed["os"] == expected["os"], "OS package coverage differs from image records")
    if role == "egress":
        require("squid" in packages, "Missing proxy package inventory")
    else:
        require(expected.get("python") and expected.get("node"), "Missing expected gateway runtime inventory")
        require(expected["python"] <= observed["python"] and expected["node"] <= observed["node"],
                "Missing gateway Python/Node package coverage")
    require(licenses, "Missing license inventory")
    summary = {"image_id": image_id, "role": role, "scanner": VERSION,
               "os_packages": len(packages), "license_entries": len(licenses),
               "vulnerabilities": counts, "secret_findings": secret_count,
               "production_approved": False}
    # No raw match, path, token, financial data or remote error enters diagnostics.
    require(not secret_count, "Secret findings block artifact review")
    require(not counts["UNKNOWN"], "Unclassified vulnerabilities need review")
    require(not counts["HIGH"] and not counts["CRITICAL"], "HIGH/CRITICAL vulnerabilities block artifact review")
    return summary


def audit(archive, filesystem, image_id, role, scanner, cache):
    require(os.name == "posix", "Use the documented disposable Linux audit runner")
    require(scanner.is_file() and not scanner.is_symlink(), "Expected pinned scanner file")
    require(hashlib.sha256(scanner.read_bytes()).hexdigest() == BINARY_SHA256, "Scanner binary hash mismatch")
    require(archive.is_file() and not archive.is_symlink(), "Expected exported image archive")
    require(DIGEST.fullmatch(image_id), "Invalid expected image ID")
    expected = inventory(filesystem, role)
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(not cache.is_symlink() and cache.stat().st_uid == os.geteuid() and
            cache.stat().st_mode & 0o077 == 0, "Scanner cache must be owned and private")
    with tempfile.TemporaryDirectory(prefix="ynab-image-audit-") as directory:
        work = Path(directory)
        (work / "config.yaml").write_text("{}\n")
        (work / "ignore").write_text("")
        report_path = work / "report.json"
        # Exclude scanner overrides, registry tokens and user configuration.
        environment = {key: os.environ[key] for key in ("PATH", "SSL_CERT_FILE", "SSL_CERT_DIR") if key in os.environ}
        environment.update(HOME=str(work), TMPDIR=str(work), NO_COLOR="1")
        command = [str(scanner.resolve()), "image", "--input", str(archive.resolve()),
                   "--scanners", "vuln,secret,license", "--list-all-pkgs", "--license-full",
                   "--format", "json", "--output", str(report_path), "--cache-dir", str(cache.resolve()),
                   "--config", str(work / "config.yaml"), "--ignorefile", str(work / "ignore"),
                   "--secret-config", "",
                   "--ignore-unfixed=false", "--exit-code", "0", "--skip-version-check", "--quiet", "--timeout", "5m"]
        try:
            result = subprocess.run(command, env=environment, capture_output=True, timeout=330)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise AuditError("Scanner unavailable or timed out") from error
        require(result.returncode == 0, "Scanner failed; no artifact approval")
        database = json.loads((cache / "db/metadata.json").read_text())
        now = datetime.now(timezone.utc)
        require(database.get("Version") == 2 and
                timedelta(minutes=-5) <= now - timestamp(database.get("UpdatedAt")) <= timedelta(hours=48) and
                timestamp(database.get("NextUpdate")) > now, "Scanner vulnerability database is stale/incomplete")
        require(report_path.stat().st_size <= 50_000_000, "Scanner report exceeds limit")
        data = report_path.read_bytes()
        # Retain diagnostic evidence privately even when the policy rejects it.
        # Never upload these reports as CI artifacts: secret matches may appear.
        evidence = cache / ("audit-" + uuid.uuid4().hex + ".json")
        fd = os.open(evidence, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        return validate(json.loads(data), image_id, role, expected, now)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--filesystem", type=Path, required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--role", choices=("gateway", "egress"), required=True)
    parser.add_argument("--scanner", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    try:
        audit(args.archive, args.filesystem, args.image_id, args.role, args.scanner, args.cache)
        print("YNAB image audit passed; separate production approval remains required")
    except (AuditError, OSError, ValueError, TypeError, KeyError, AttributeError, tarfile.TarError) as error:
        # Never print untrusted JSON or scanner stderr (secret scanner matches).
        print("YNAB image audit blocked: " + (str(error) if isinstance(error, AuditError) else "incomplete evidence"))
        raise SystemExit(1)
