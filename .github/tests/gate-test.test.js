"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const YAML = require("yaml");

const root = path.resolve(__dirname, "../..");

const workflow = YAML.parse(fs.readFileSync(path.join(root, ".github/workflows/gate-test.yml"), "utf8"));

const steps = new Map(workflow.jobs.validate.steps.map((step) => [step.id, step]));

const filters = YAML.parse(steps.get("filter").with.filters);

test("changed paths select independent checks", () => {
  for (const [file, expected] of [
    [".github/package.json", ["automation"]], [".github/package-lock.json", ["automation"]],
    ["CHANGELOG.md", []], ["compose.yml", ["compose"]], [".env", ["compose"]],
    ["gateway/nginx/vhosts/example.conf", ["compose"]], ["deploy/workflow.yml", ["release"]],
    [".github/actions/example/action.yml", ["automation"]], [".github/tests/gate-test.test.js", ["automation"]],
    [".github/tests/integration/gateway.test.js", ["compose", "automation"]],
    [".github/scripts/run-release-consumer-tests.js", ["release", "automation"]],
    ["uv.lock", ["release", "automation"]], [".github/workflows/gate-test.yml", ["compose", "release", "automation"]],
    [".github/workflows/ci-orchestrator.yml", ["compose", "release", "automation"]],
  ]) {
    const scopes = Object.keys(filters).filter((name) => filters[name].some((pattern) => path.posix.matchesGlob(file, pattern)));
    assert.deepEqual(new Set(scopes), new Set(expected), file);
  }
});

test("scope detection rejects failures and incomplete results", (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "gate-test-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const summary = path.join(directory, "summary");
  const step = steps.get("scope");
  assert.equal(step.shell, "node {0}");
  const defaults = { OUTCOME: "success", COMPOSE: "false", RELEASE: "false", AUTOMATION: "false" };
  for (const [changed, expected] of [
    [{}, 0], [{ RELEASE: "true" }, 0], [{ OUTCOME: "failure" }, 1],
    [{ RELEASE: "" }, 1], [{ AUTOMATION: "unexpected" }, 1],
  ]) {
    fs.writeFileSync(summary, "");
    const result = spawnSync(process.execPath, ["-e", step.run], {
      cwd: root, encoding: "utf8", timeout: 10000,
      env: { ...process.env, GITHUB_STEP_SUMMARY: summary, ...defaults, ...changed },
    });
    assert.ifError(result.error);
    assert.equal(result.status, expected, result.stderr);
    if (expected) {
      assert.match(result.stdout, /Test path detection unavailable/);
      assert.match(fs.readFileSync(summary, "utf8"), /Test path detection unavailable/);
    }
  }
});
