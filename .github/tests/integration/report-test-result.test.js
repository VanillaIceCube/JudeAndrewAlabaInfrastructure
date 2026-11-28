"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const YAML = require("yaml");

const root = path.resolve(__dirname, "../../..");

const workflow = YAML.parse(fs.readFileSync(path.join(root, ".github/workflows/gate-test.yml"), "utf8"));

const steps = new Map(workflow.jobs.validate.steps.map((step) => [step.id, step]));

test("reports distinguish out-of-scope and failed checks", (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "report-test-result-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const output = path.join(directory, "outputs");
  const summary = path.join(directory, "summary");
  for (const [name, source] of [["ingress", "ingress.log"], ["release", "release-tests.log"], ["automation", "automation.log"]]) {
    const command = steps.get(name + "-report").run.trim();
    assert.equal(command, "node .github/scripts/report-test-result.js " + name);
    fs.writeFileSync(path.join(directory, source), "Synthetic check diagnostics\n");
    for (const [scope, applicable, outcome, expected] of [
      ["success", "false", "skipped", "not-applicable"], ["failure", "", "skipped", "failure"],
      ["success", "true", "skipped", "failure"], ["success", "true", "success", "success"], ["success", "true", "failure", "failure"],
    ]) {
      fs.writeFileSync(output, "");
      fs.writeFileSync(summary, "");
      const result = spawnSync(process.execPath, [".github/scripts/report-test-result.js", name], {
        cwd: root, encoding: "utf8", timeout: 10000,
        env: { ...process.env, GITHUB_OUTPUT: output, GITHUB_STEP_SUMMARY: summary, RUNNER_TEMP: directory,
          SCOPE: scope, APPLICABLE: applicable, AUTOMATION: applicable, OUTCOME: outcome },
      });
      assert.ifError(result.error);
      assert.equal(result.status, 0, result.stderr);
      const values = fs.readFileSync(output, "utf8");
      assert.ok(values.startsWith(name + "_status=" + expected + "\n"), values);
      if (["success", "failure"].includes(outcome)) {
        assert.match(values, /Synthetic check diagnostics/);
        assert.ok(fs.statSync(path.join(directory, source.replace(/\.log$/, ".bounded.txt"))).isFile());
      }
    }
  }
});
