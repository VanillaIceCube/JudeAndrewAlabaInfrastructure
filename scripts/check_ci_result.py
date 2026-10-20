"""Fail closed unless all expected gates and applicable reviewers succeeded."""
import json
import os
from pathlib import Path

GATES = {"lints", "tests", "codeql", "dependency-vulnerability", "dependency-malware", "secrets"}
REVIEWS = {"code-review", "build-review", "security-review"}


def reviews_applicable(event, repository):
    """Human and Dependabot PRs from this repository require every reviewer."""
    head_repository = event.get("pull_request", {}).get("head", {}).get("repo") or {}
    return bool(repository and head_repository.get("full_name") == repository)


def failures(results, reviews_applicable):
    problems = []
    for name in sorted(GATES | REVIEWS):
        expected = "skipped" if name in REVIEWS and not reviews_applicable else "success"
        result = results.get(name, {}).get("result", "missing")
        if result != expected:
            problems.append(f"{name}: {result} (expected {expected})")
    return problems


if __name__ == "__main__":
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    applicable = reviews_applicable(event, os.environ["GITHUB_REPOSITORY"])
    problems = failures(json.loads(os.environ["RESULTS"]), applicable)
    if problems:
        raise SystemExit("\n".join(problems))
    print("All independent gates and applicable reviews passed. Owner merge approval remains required.")
