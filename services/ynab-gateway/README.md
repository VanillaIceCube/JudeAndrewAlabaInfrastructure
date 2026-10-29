# 🔐 YNAB authenticated gateway preparation

This directory currently contains the reviewed dependency lock for #59, not a
deployable gateway. No listener, OAuth provider, credential, network or deployment
is configured. Production activation remains blocked.

## 📌 Maintained fallback and pins

The conditional Supergateway 4.2.1 choice in #57 remains blocked by high/critical
runtime advisories. Reopen that choice in favor of **FastMCP 4.1.4**, using
`fastmcp-slim[server,client]==4.1.4`; its maintained stateful proxy and resource-server
authentication APIs avoid owning another MCP protocol engine. The full upstream
source commit is `26bf9080ae338d1467dca6471b15c6911f71c75c` (Apache-2.0).
Oliver's unchanged application and canonical source pins remain under
[`../ynab-mcp`](../ynab-mcp/README.md). No fork or dependency overrides.

`requirements.txt` pins the complete Linux/Python 3.12 graph with SHA-256 artifact
hashes. Generate updates in a disposable Linux container using Python 3.12,
`pip==26.2` and `pip-tools==7.6.2`, with this single input line in a temporary
`requirements.in` (do not add another unscanned manifest):

```text
fastmcp-slim[server,client]==4.1.4
```

```sh
pip-compile --generate-hashes --resolver=backtracking --strip-extras \
  --no-emit-index-url --no-emit-trusted-host \
  --output-file=requirements.txt requirements.in
python scripts/check_gateway_dependencies.py
```

Install only using `pip install --require-hashes -r requirements.txt` in a disposable
environment. Hashes identify downloaded bytes; they do not authenticate the
publisher or prove absence of malicious code. Review new dependencies, artifacts,
licenses and provenance on every update. Build tools are not runtime dependencies.

## 🛡️ Existing CI boundary

The existing dependency-scope gate now supports this **exact** lock path. All
other package manifests continue to fail closed until scanner support is reviewed.
It validates exact versions/hashes without installing packages, queries the
[OSV batch API](https://google.github.io/osv.dev/post-v1-querybatch/) for all pins,
and checks each hash and yank status against the
[PyPI release JSON API](https://docs.pypi.org/api/json/).
Known advisories at any severity, catalogued malware, incomplete/unavailable
metadata, pagination and redirects fail the gate. Only package names, versions
and public hashes are sent; no provider account APIs or credentials are involved.

These checks do not detect unknown malware or scan container layers, and do not
grant license/provenance approval. #61 retains full-image and release acceptance.
The initial 2026-10-29 scan of 61 pinned packages found no known OSV advisories;
repeat the live check rather than treating that result as permanent.

## 🧪 Required next acceptance

This prerequisite PR includes no FastMCP runtime acceptance harness. The existing
Supergateway experiment does not validate the replacement. #59 must implement
and test strict issuer/audience/owner/client
identity, expiry/scopes, principal-bound sessions, Host/Origin, quotas, child failure,
safe readiness and error/log redaction. No public route or OAuth client readiness
is established by this dependency PR. `YNAB_ALLOW_WRITES=0` remains mandatory.
