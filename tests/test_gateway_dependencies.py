"""Fail-closed lock and authoritative metadata boundary tests; no network."""
import unittest
from scripts import check_gateway_dependencies as deps
from scripts.check_dependency_scope import unsupported_manifests

H = "a" * 64
PACKAGE = ("example", "1.2.3", {H})


class GatewayDependencyTests(unittest.TestCase):
    def test_hashes_and_versions_required_without_options_or_duplicate_names(self):
        self.assertEqual(deps.parse_lock(f"# generated\nexample==1.2.3 \\\n --hash=sha256:{H}\n"), [PACKAGE])
        for text in ("", "example>=1", "example==1", "-r other.txt",
                     f"example==1 --hash=md5:{H}", f"example==1 --hash=sha256:{H};linux",
                     f"example==1 --hash=sha256:{H} --index-url=https://bad.example",
                     f"example==1 --hash=sha256:{H}\nexample==2 --hash=sha256:{H}",
                     f"example==1 \\\n --hash=sha256:{H} \\\n"):
            with self.subTest(text=text), self.assertRaises(deps.AuditError):
                deps.parse_lock(text)

    def test_only_exact_gateway_lock_is_supported(self):
        self.assertEqual(unsupported_manifests([deps.LOCK, deps.AUTH_LOCK]), [])
        for path in ("other/requirements.txt", "services/ynab-gateway/requirements.in",
                     "services/ynab-gateway/pyproject.toml", "services/ynab-gateway/package.json",
                     "services/mcp-auth/requirements.in", "services/mcp-auth/pyproject.toml"):
            self.assertEqual(unsupported_manifests([path]), [path])

    def test_osv_batch_shape_pagination_and_all_advisories_fail_closed(self):
        def clean(url, payload):
            self.assertEqual(url, "https://api.osv.dev/v1/querybatch")
            self.assertEqual(payload["queries"][0]["version"], "1.2.3")
            return {"results": [{}]}
        deps.check_osv([PACKAGE], clean)
        for result in ({}, {"results": [{}], "error": "unavailable"},
                       {"results": []}, {"results": [None]},
                       {"results": [{"next_page_token": "more"}]},
                       {"results": [{"vulns": [{"id": "MAL-2026-1"}]}]},
                       {"results": [{"vulns": [{"id": "GHSA-example"}]}]},
                       {"results": [{"vulns": [{}]}]},
                       {"results": [{"vulns": "malformed"}]},
                       {"results": [{"error": "unavailable"}]}):
            with self.subTest(result=result), self.assertRaises(deps.AuditError):
                deps.check_osv([PACKAGE], lambda *_: result)

    def test_release_identity_hash_and_yank_status_required(self):
        def release(digest=H, yanked=False, name="example", version="1.2.3"):
            return {"info": {"name": name, "version": version},
                    "urls": [{"digests": {"sha256": digest}, "yanked": yanked}]}
        deps.check_release(PACKAGE, lambda _: release())
        for result in ({}, release(digest="b" * 64), release(yanked=True),
                       release(yanked=None), release(name="other"), release(version="1.2.4")):
            with self.subTest(result=result), self.assertRaises(deps.AuditError):
                deps.check_release(PACKAGE, lambda _: result)

    def test_redirects_cannot_send_requests_to_another_origin(self):
        with self.assertRaises(deps.AuditError):
            deps.NoRedirect().redirect_request(None, None, 302, "", {}, "http://127.0.0.1/")


if __name__ == "__main__":
    unittest.main()
