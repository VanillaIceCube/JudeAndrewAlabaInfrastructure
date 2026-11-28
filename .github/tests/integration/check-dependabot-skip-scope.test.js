"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const YAML = require("yaml");
const { scopeAllowsSkip } = require("../../scripts/check-dependabot-skip-scope");

test("recognizes the published CodeQL check names when a language is skipped", () => {
  const workflow = path.join(__dirname, "../../workflows/alert-codeql.yml");
  const { jobs } = YAML.parse(fs.readFileSync(workflow, "utf8"));
  const python = `CodeQL / ${jobs["analyze-python"].name}`;
  const javascript = `CodeQL / ${jobs["analyze-javascript"].name}`;
  const actions = `CodeQL / ${jobs["analyze-actions"].name}`;
  for (const name of [python, javascript, actions]) {
    assert.equal(scopeAllowsSkip(name, ["README.md"]), true);
    assert.equal(scopeAllowsSkip(name, []), true);
    assert.equal(scopeAllowsSkip(name, [".github/workflows/ci-auto-merge.yml"]), false);
  }
  for (const file of ["backend/uv.lock", "root.py", "tools/worker.py", "pyproject.toml", "uv.lock"]) {
    assert.equal(scopeAllowsSkip(python, [file]), false);
    assert.equal(scopeAllowsSkip(javascript, [file]), true);
    assert.equal(scopeAllowsSkip(actions, [file]), false);
  }
  for (const file of ["frontend/package-lock.json", "tool.ts", "nested/script.cjs"]) {
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
