# 🔒 YNAB CONNECT artifact

This is application-specific packaging of maintained Canonical Squid with two
official Ubuntu security packages. Oliver's source remains unchanged. The fixed
CONNECT authority/ACL and topology remain in the
[inactive network contract](../../docs/ynab-ingress.md).

The amd64 base is pinned by digest in `Dockerfile`; it preserves native dpkg
inventory, unlike the evaluated newer Rock. Its four HIGH OpenSSL findings are
fixed with `libssl3t64` and `openssl` **3.0.13-0ubuntu3.16**, both version- and
SHA-256-pinned `ADD` inputs. Package bytes were independently matched to SHA-512
hashes obtained through verified Ubuntu apt repository metadata. Installation
uses `RUN --network=none`, with no mutable apt resolver or extra package source.
Publisher outages/removal or changed bytes fail the build; refresh only through
a reviewed source/manifest update. The package manager preserves native package
and license records. Review Ubuntu/Squid notices and source obligations before
redistribution; this recipe is not license or provenance approval.

```sh
python services/ynab-egress/build.py --tag ynab-egress-candidate:local \
  --record /private/new-egress-build.json
python services/ynab-gateway/run_tests.py
```

The builder verifies `manifest.json`, uses an empty context containing only the
recipe, and records an unpublished/unapproved local image ID. It never pushes an
image. Run the [full-image paired artifact prerequisite](../../docs/ynab-artifact-security.md)
on each exact final artifact and review all remaining findings before release.
The initial evaluation (2026-10-29) covered 138 OS packages with zero HIGH/CRITICAL/
UNKNOWN findings or secret matches; 255 MEDIUM and 24 LOW findings still need
applicability review. A past result does not approve a later build.

The existing gateway runner builds this recipe under its unique fixture identity,
then tests the production ACL, resolved-destination denial, direct-path isolation
and real unchanged stdio reads through CONNECT using a synthetic TLS API.
It removes only that run's fixture image. The final image defaults to uid/gid 13,
and Compose still enforces read-only/capability/resource/network controls. An
image's `EXPOSE 3128` metadata does not publish a host port; Compose publishes none.

Production uses the independent immutable
`YNAB_EGRESS_REPOSITORY`/`YNAB_EGRESS_SHA256` pair. No registry artifact exists or is
approved merely because this source is merged. No credentials, route/network
activation, restart policy or production deployment is introduced here.
