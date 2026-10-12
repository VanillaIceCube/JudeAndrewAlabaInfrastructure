"""Fail closed unless all expected gates and applicable reviewers succeeded."""
import json
import os

GATES = {"lints", "tests", "codeql", "dependency-vulnerability", "dependency-malware", "secrets"}
REVIEWS = {"code-review", "build-review", "security-review"}


def failures(results, reviews_applicable):
    problems = []
    for name in sorted(GATES | REVIEWS):
        expected = "skipped" if name in REVIEWS and not reviews_applicable else "success"
        result = results.get(name, {}).get("result", "missing")
        if result != expected:
            problems.append(f"{name}: {result} (expected {expected})")
    return problems


if __name__ == "__main__":
    problems = failures(json.loads(os.environ["RESULTS"]), os.environ["REVIEWS_APPLICABLE"] == "true")
    if problems:
        raise SystemExit("\n".join(problems))
    print("All independent gates and applicable reviews passed. Owner merge approval remains required.")
