# 🛡️ YNAB artifact review

This is the #61 artifact prerequisite. Source CI and synthetic acceptance do not
approve a production image. Keep credentials, public activation and `env-prod`
held until this gate and the independent release/rollback and #62 operator gates
are satisfied. No scanner exception is implicit in a source merge.

## 🔎 Credential-free full-image scan

Build the gateway with its existing verified builder. Export that exact local
image and the pinned egress image with `docker image save`. Record the image ID
from `docker image inspect` alongside source SHA, upstream commit, source manifest,
registry manifest/platform digest (when published) and build evidence. An image ID
identifies local content; it is not a registry manifest digest or publisher proof.
Also `docker create` a uniquely named, network-disabled container from that exact
image, inspect its `Image` ID for equality, and `docker export` its filesystem
without ever starting it. Remove only that temporary container and its anonymous
volumes. Bind both exports to the same image in the private evidence record.

Use Linux amd64 and the official
[Trivy 0.76.1 release](https://github.com/aquasecurity/trivy/releases/tag/v0.76.1).
Verify the Linux-64bit archive SHA-256 before extracting only its `trivy` binary:

```text
archive c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0
binary  d1dfca6ae10a1ad4540bb94e64f0510077c47008920a9b554986b39dca573d83
```

The runner checks the extracted binary hash itself. Use a disposable Linux
workstation/container with a private mode-0700 cache and no credentials or Docker
socket. Mount only the archive, scanner, source script and private cache needed:

```sh
python3 scripts/check_ynab_image_audit.py \
  --archive /private/candidate.tar --filesystem /private/filesystem.tar \
  --image-id sha256:EXACT_LOCAL_IMAGE_ID \
  --role egress --scanner /tools/trivy --cache /private/trivy-cache
```

Use `--role gateway` for the app image. The command controls the configuration,
empty ignore list, all three scanners and fresh vulnerability database. It does
not execute image code. It rejects scanner errors/timeouts, wrong image/version/
architecture, stale evidence, absent/thin OS inventory, absent role-specific
package or license inventory, unclassified vulnerabilities, any secret finding
and all HIGH/CRITICAL CVEs, including unfixed ones. Raw matches and scanner stderr
never enter stdout. A mode-0600 `audit-*.json` report is retained in the private
cache even on a policy rejection for applicability review; never upload it as a
public/CI artifact. Temporary work files are removed. Keep exported images private:
they must be built without credentials. Lower-severity findings remain visible in
the count summary and require applicability review, rather than blanket approval.
The independent filesystem reader extracts nothing and executes no image code.
It compares all installed Debian/Ubuntu package names/versions with the scan,
and requires coverage for every installed Node lock and gateway Python metadata
record. A package-count threshold alone cannot establish coverage. An absent
native package database or installed runtime lock fails closed. This is coverage
of recorded packages; untracked/copied binaries still need source/base provenance
review, including the two Node runtime libraries copied into the Python base.

Repository CI tests the fail-closed policy without metadata requests. This
prerequisite does not silently label the currently vulnerable candidate clean or
make every unrelated source PR depend on an unapproved production artifact.
The release path must require fresh evidence for **both** exact images; hand-edited
JSON or an old successful scan is not a release authorization.

## 🚧 Current blockers and limits

The #60 Squid digest `8fafd41d6ddceb295d26eea9938321d825ac5351c7e46cf6a8aa5d093b8ed1ce`
has five HIGH OS findings in the 2026-10-29 scan: CVE-2025-68973 (gpgv),
CVE-2026-45447 and CVE-2026-84782 (OpenSSL/library entries). It is a test/source
candidate, **not approved for production**. Update a maintained upstream artifact
and re-run the complete egress/container suites and audit; do not suppress these
findings or patch/fork Oliver's application.

A newer Canonical Ubuntu 26.04 Rock candidate exposes an OS label but no
Trivy-recognized OS package inventory. Its zero reported OS findings cannot pass
this gate. A supported, complete publisher SBOM/catalog path or a scan-compatible
maintained artifact is needed before adoption. Do not synthesize missing package
source/version metadata to manufacture coverage.

License inventory is evidence for review, not legal approval: classify Oliver's
and FastMCP's licenses, all shipped dependencies, Squid's GPL notices/source
obligations and base-image licenses before redistribution. License severity is
not CVE severity. Review publisher origin, pinned hashes and build/source parity
separately; scanning does not establish provenance or detect unknown malware.
Existing OSV/PyPI lock checks, secret scanning and synthetic contract tests remain
required. Neither a local scan nor passing CI supplies the real-client/provider
acceptance or capacity evidence required by #62.
