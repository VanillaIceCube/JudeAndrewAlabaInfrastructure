"""Security boundary regressions for repository automation."""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dependency_scope", ROOT / "scripts/check_dependency_scope.py")
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)
spec = importlib.util.spec_from_file_location("ci_result", ROOT / "scripts/check_ci_result.py")
ci_result = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci_result)


class AutomationPolicyTests(unittest.TestCase):
    def test_package_manifests_require_explicit_scanner_setup(self):
        self.assertEqual(scope.unsupported_manifests(["compose.yml", "scripts/release.py", "action.yml"]), [])
        for manifest in ("frontend/package.json", "backend/requirements-prod.txt", "pyproject.toml", "uv.lock", "go.mod"):
            with self.subTest(manifest=manifest):
                self.assertEqual(scope.unsupported_manifests([manifest]), [manifest])

    def test_external_actions_are_immutable_and_review_workflows_cannot_merge_or_deploy(self):
        for path in (ROOT / ".github").rglob("*.yml"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertNotIn("pull_request_target", text)
                self.assertNotIn("ci-auto-merge.yml", text)
                self.assertNotRegex(text, r"gh\s+pr\s+merge|enablePullRequestAutoMerge|mergePullRequest")
                self.assertNotRegex(text, r"contents:\s*write")
                if path.name != "deploy-gateway.yml":
                    self.assertNotIn("GATEWAY_SSH_KEY", text)
                    self.assertNotIn("DEPLOY_SSH_KEY", text)
                for action in re.findall(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", text, re.M):
                    if not action.startswith("./"):
                        self.assertRegex(action, r"^[\w./-]+@[a-f0-9]{40}$")

    def test_fork_and_dependabot_secrets_are_never_requested(self):
        text = (ROOT / ".github/workflows/ci-orchestrator.yml").read_text()
        self.assertEqual(text.count("if: always() && github.event.pull_request.head.repo.full_name == github.repository && github.event.pull_request.user.login != 'dependabot[bot]'"), 2)
        self.assertIn("REVIEWS_APPLICABLE:", text)
        self.assertNotIn("secrets: inherit", text)

    def test_aggregate_requires_every_gate_and_review(self):
        results = {name: {"result": "success"} for name in ci_result.GATES | ci_result.REVIEWS}
        self.assertEqual(ci_result.failures(results, True), [])
        for state in ("failure", "cancelled", "skipped", "unknown"):
            with self.subTest(state=state):
                altered = {**results, "codeql": {"result": state}}
                self.assertTrue(ci_result.failures(altered, True))
        self.assertTrue(ci_result.failures({}, True))

    def test_only_inapplicable_reviews_may_skip(self):
        results = {name: {"result": "success"} for name in ci_result.GATES}
        results.update({name: {"result": "skipped"} for name in ci_result.REVIEWS})
        self.assertEqual(ci_result.failures(results, False), [])
        self.assertTrue(ci_result.failures(results, True))
        results["tests"] = {"result": "skipped"}
        self.assertTrue(ci_result.failures(results, False))


if __name__ == "__main__":
    unittest.main()
