"""Security boundary regressions for repository automation."""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
from scripts import check_dependency_scope as scope
spec = importlib.util.spec_from_file_location("ci_result", ROOT / "scripts/check_ci_result.py")
ci_result = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci_result)


class AutomationPolicyTests(unittest.TestCase):
    def test_gateway_credentials_are_limited_to_owner_production_transport(self):
        text = (ROOT / ".github/workflows/deploy-gateway.yml").read_text()
        self.assertNotRegex(text, r"(?m)^\s*environment:")
        self.assertNotIn("deployments:", text)
        self.assertNotIn("actions: read", text)
        self.assertIn("branches: [env-prod]", text)
        self.assertIn("github.ref == 'refs/heads/env-prod'", text)
        self.assertIn("vars.DEPLOY_ENABLED == 'true'", text)
        self.assertIn("github.actor == github.repository_owner", text)
        self.assertIn("github.triggering_actor == github.repository_owner", text)
        self.assertIn("cancel-in-progress: false", text)
        self.assertNotRegex(text, r"pull_request|workflow_call|secrets: inherit")
        authorize = text.index("run: python3 scripts/gateway_transport.py authorize")
        credential = text.index("DEPLOY_SSH_KEY: ${{ secrets.DEPLOY_SSH_KEY }}")
        self.assertLess(authorize, credential)
        finalizer = text[text.index("      - name: Report a failed or cancelled runner"):]
        self.assertIn("if: always() && steps.release.outcome != 'success'", finalizer)
        self.assertIn("GATEWAY_RUNNER_STATUS: ${{ job.status }}", finalizer)
        self.assertNotIn("GH_TOKEN", finalizer)
        self.assertNotIn("secrets.", finalizer)
        for name in ("review-code.yml", "review-security.yml"):
            policy = (ROOT / ".github/workflows" / name).read_text()
            self.assertNotIn("branch-restricted credentials", policy)
            self.assertIn("repository Actions secrets/variables only", policy)
            self.assertIn("Repository secret access is not branch-scoped", policy)

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

    def test_reviewer_workflow_guards_exclude_forks_without_excluding_dependabot(self):
        text = (ROOT / ".github/workflows/ci-orchestrator.yml").read_text()
        for job, prefix in (("code-review", ""), ("build-review", "always() && "), ("security-review", "always() && ")):
            with self.subTest(job=job):
                block = re.search(rf"(?ms)^  {job}:\n(.*?)(?=^  [\w-]+:|\Z)", text).group(1)
                guard = re.search(r"^    if: (.+)$", block, re.M).group(1)
                self.assertEqual(guard, prefix + "github.event.pull_request.head.repo.full_name == github.repository")
                self.assertNotIn("secrets: inherit", block)
        self.assertNotIn("pull_request.user.login", text)
        self.assertNotIn("REVIEWS_APPLICABLE:", text)
        self.assertIn("run: python3 scripts/check_ci_result.py", text)

    def test_ci_result_requires_reviews_for_human_and_dependabot_prs_only_from_this_repo(self):
        repository = "VanillaIceCube/JudeAndrewAlabaInfrastructure"
        for author in ("VanillaIceCube", "dependabot[bot]"):
            for head_repository, expected in ((repository, True), ("someone/fork", False), (None, False)):
                with self.subTest(author=author, head_repository=head_repository):
                    event = {
                        "pull_request": {
                            "user": {"login": author},
                            "head": {"repo": {"full_name": head_repository} if head_repository else None},
                        }
                    }
                    applicable = ci_result.reviews_applicable(event, repository)
                    self.assertEqual(applicable, expected)
                    results = {name: {"result": "success"} for name in ci_result.GATES}
                    results.update({name: {"result": "skipped"} for name in ci_result.REVIEWS})
                    self.assertEqual(bool(ci_result.failures(results, applicable)), expected)
        self.assertFalse(ci_result.reviews_applicable({}, repository))
        self.assertFalse(ci_result.reviews_applicable({"pull_request": {"head": {"repo": {"full_name": ""}}}}, ""))

    def test_aggregate_requires_every_gate_and_review(self):
        results = {name: {"result": "success"} for name in ci_result.GATES | ci_result.REVIEWS}
        self.assertEqual(ci_result.failures(results, True), [])
        for name in ci_result.GATES | ci_result.REVIEWS:
            for state in ("failure", "cancelled", "skipped", "unknown"):
                with self.subTest(name=name, state=state):
                    altered = {**results, name: {"result": state}}
                    self.assertTrue(ci_result.failures(altered, True))
            with self.subTest(name=name, state="missing"):
                altered = {key: value for key, value in results.items() if key != name}
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
