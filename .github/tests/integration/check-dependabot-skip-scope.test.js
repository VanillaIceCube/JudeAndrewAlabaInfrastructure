"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { scopeAllowsSkip } = require("../../scripts/check-dependabot-skip-scope");

test("matches changed files against CodeQL filters", () => {
  const python = "CodeQL / Analyze Python";
  const javascript = "CodeQL / Analyze JavaScript/TypeScript";
  const actions = "CodeQL / Analyze GitHub Actions";
  for (const name of [python, javascript, actions]) {
    assert.equal(scopeAllowsSkip(name, ["README.md"]), true);
    assert.equal(scopeAllowsSkip(name, []), true);
    assert.equal(scopeAllowsSkip(name, [".github/workflows/ci-auto-merge.yml"]), false);
  }
  for (const file of ["root.py", "tools/worker.py", "pyproject.toml", "uv.lock"]) {
    assert.equal(scopeAllowsSkip(python, [file]), false);
    assert.equal(scopeAllowsSkip(actions, [file]), false);
  }
  for (const file of ["tool.ts", "nested/script.cjs"]) {
    assert.equal(scopeAllowsSkip(javascript, [file]), false);
    assert.equal(scopeAllowsSkip(actions, [file]), false);
    assert.equal(scopeAllowsSkip(python, [file]), true);
  }
});

test("requires checks for changes to the auto-merge and CI workflows", () => {
  for (const file of [".github/workflows/ci-auto-merge.yml", ".github/workflows/ci-orchestrator.yml"]) {
    assert.equal(scopeAllowsSkip("CodeQL / Analyze GitHub Actions", [file]), false, file);
  }
});

test("matches changed files against lint and test filters", () => {
  const automation = "Tests / Automation Tests (Node)";
  const frontend = "Tests / Frontend Tests (React)";
  assert.equal(scopeAllowsSkip(automation, ["frontend/package.json"]), true);
  assert.equal(scopeAllowsSkip(frontend, ["frontend/package.json"]), false);
  for (const file of [".github/package.json", ".github/package-lock.json"]) {
    assert.equal(scopeAllowsSkip(automation, [file]), false);
    assert.equal(scopeAllowsSkip(frontend, [file]), true);
  }
  for (const [name, file] of [
    ["Lints / Lint Frontend (ESLint + Prettier)", "frontend/package.json"],
    ["Lints / Lint Backend (Ruff)", "backend/uv.lock"],
    ["Tests / Frontend Tests (React)", "frontend/package-lock.json"],
    ["Tests / Backend Tests (Django)", "backend/config/settings.py"],
    ["Tests / Automation Tests (Node)", "backend/docker/Dockerfile.hotswap"],
  ]) {
    assert.equal(scopeAllowsSkip(name, [file]), false, name);
    assert.equal(scopeAllowsSkip(name, ["LICENSE"]), true, name);
  }
});
