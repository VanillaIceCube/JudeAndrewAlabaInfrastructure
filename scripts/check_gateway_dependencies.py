"""Audit the one supported Python lock without installing or executing packages.

OSV includes catalogued PyPI malware; this is not an unknown-malware scanner.
Only official HTTPS metadata APIs are contacted, with no redirects or credentials.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
LOCK = "services/ynab-gateway/requirements.txt"
AUTH_LOCK = "services/mcp-auth/requirements.txt"
PIN = re.compile(r"([a-z0-9]+(?:[._-][a-z0-9]+)*)==([0-9][a-zA-Z0-9.!+_-]*)")
HASH = re.compile(r"--hash=sha256:([a-f0-9]{64})")


class AuditError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AuditError("Metadata redirects are not allowed")


def fetch(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    request = Request(url, data=body, headers={
        "Accept": "application/json", "Content-Type": "application/json",
        "User-Agent": "Infrastructure-dependency-check/1",
    })
    try:
        with build_opener(NoRedirect).open(request, timeout=20) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise AuditError("Metadata response exceeds limit")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise AuditError("Metadata response is not an object")
        return result
    except (URLError, TimeoutError, OSError, ValueError) as error:
        # Do not print remote bodies, request headers or error URLs.
        raise AuditError("Dependency metadata unavailable or malformed") from error


def parse_lock(text):
    """Accept exact pins plus SHA-256 hashes only; no pip options, URLs or markers."""
    packages = []
    pending = ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        continued = line.endswith("\\")
        pending += " " + (line[:-1] if continued else line)
        if continued:
            continue
        words = pending.split()
        pending = ""
        pin = PIN.fullmatch(words[0])
        hashes = [HASH.fullmatch(word) for word in words[1:]]
        if not pin or not hashes or not all(hashes):
            raise AuditError("Lock must contain only exact versions and SHA-256 hashes")
        name, version = pin.groups()
        name = re.sub(r"[-_.]+", "-", name)
        if any(item[0] == name for item in packages):
            raise AuditError("Duplicate package pin")
        packages.append((name, version, {match.group(1) for match in hashes}))
    if pending or not 1 <= len(packages) <= 100:
        raise AuditError("Incomplete or unsupported lock size")
    return packages


def check_osv(packages, request=fetch):
    result = request("https://api.osv.dev/v1/querybatch", {"queries": [
        {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
        for name, version, _ in packages
    ]})
    if not isinstance(result, dict) or set(result) != {"results"}:
        raise AuditError("Unexpected OSV batch response")
    rows = result.get("results")
    if not isinstance(rows, list) or len(rows) != len(packages):
        raise AuditError("Incomplete OSV batch response")
    findings = []
    for (name, version, _), row in zip(packages, rows):
        if not isinstance(row, dict) or set(row) - {"vulns", "next_page_token"}:
            raise AuditError("Unexpected OSV result")
        # Any pagination means evidence is incomplete; never silently ignore it.
        if row.get("next_page_token"):
            raise AuditError("OSV pagination requires review")
        vulns = row.get("vulns", [])
        if not isinstance(vulns, list):
            raise AuditError("Malformed OSV findings")
        for vuln in vulns:
            identifier = vuln.get("id") if isinstance(vuln, dict) else None
            if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", identifier):
                raise AuditError("Malformed OSV identifier")
            findings.append(f"{name}=={version}: {identifier}")
    if findings:
        raise AuditError("Known dependency advisories: " + "; ".join(findings[:25]))


def check_release(package, request=fetch):
    name, version, hashes = package
    result = request(f"https://pypi.org/pypi/{name}/{version}/json")
    info, files = result.get("info"), result.get("urls")
    if not isinstance(info, dict) or info.get("version") != version or not isinstance(files, list) or not files:
        raise AuditError(f"{name}: incomplete PyPI release metadata")
    if re.sub(r"[-_.]+", "-", str(info.get("name", "")).lower()) != name:
        raise AuditError(f"{name}: mismatched PyPI name")
    published = set()
    for artifact in files:
        if not isinstance(artifact, dict) or not isinstance(artifact.get("digests"), dict):
            raise AuditError(f"{name}: malformed PyPI artifact")
        digest = artifact["digests"].get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise AuditError(f"{name}: malformed PyPI hash")
        if digest in hashes:
            if artifact.get("yanked") is not False:
                raise AuditError(f"{name}: locked artifact is yanked or has unknown status")
            published.add(digest)
    if published != hashes:
        raise AuditError(f"{name}: lock hashes do not match current PyPI release")


def audit(path=ROOT / LOCK):
    if path.is_symlink() or not path.is_file():
        raise AuditError("Supported lock is missing or symlinked")
    packages = parse_lock(path.read_text(encoding="utf-8"))
    check_osv(packages)
    with ThreadPoolExecutor(max_workers=8) as workers:
        list(workers.map(check_release, packages))
    return (f"Checked {len(packages)} exact hashed PyPI pins against OSV advisories (including catalogued "
            "malware) and PyPI release hashes/yanked status. No known findings. Unknown malware, source "
            "provenance, license approval and container layers require separate review; no packages executed.")


if __name__ == "__main__":
    try:
        print(audit())
    except AuditError as error:
        raise SystemExit(str(error)) from None
