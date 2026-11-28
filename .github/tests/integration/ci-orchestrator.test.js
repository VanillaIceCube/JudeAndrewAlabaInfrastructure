"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const YAML = require("yaml");

const workflow = name => YAML.parse(fs.readFileSync(path.join(".github/workflows", name + ".yml"), "utf8"));
const ci = workflow("ci-orchestrator");
const app = fs.existsSync("deploy/production/app.json");
const owner = "VanillaIceCube/";
const shared = (repo, file) => owner + repo + "/.github/workflows/" + file + ".yml@main";

test("the Actions upload omits only accepted shared workflow findings", t => {
  const file = path.join(__dirname, "../../workflows/alert-codeql.yml");
  const steps = YAML.parse(fs.readFileSync(file, "utf8")).jobs["analyze-actions"].steps;
  const [analyze, filter, upload] = steps.slice(-3);
  assert.equal(analyze.with.upload, "failure-only");
  assert.equal(upload.with.sarif_file, analyze.with.output);
  assert.equal(upload.with.category, analyze.with.category);
  const unpinned = "actions/unpinned-tag";
  const finding = (repo, ref = "main", ruleId = unpinned) => ({
    ruleId, message: { text: "Job [Job: scan](1) in 'CI' uses reusable workflow '" + repo +
      "/.github/workflows/scan.yml' with ref '" + ref + "', not a pinned commit hash" },
  });
  const keep = [finding("third-party/infrastructure"), finding("VanillaIceCube/other"),
    finding("VanillaIceCube/infrastructure", "feature"), finding("VanillaIceCube/agent-hub", "main", "other-rule"),
    { ruleId: unpinned, message: { text: "Unpinned 3rd party Action step" } }];
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "codeql-actions-"));
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }));
  const directory = path.join(temp, "codeql-actions");
  fs.mkdirSync(directory);
  const report = path.join(directory, "actions.sarif");
  const metadata = { tool: { driver: { name: "CodeQL" } } };
  fs.writeFileSync(report, JSON.stringify({ runs: [{ ...metadata, results: [
    finding("VanillaIceCube/infrastructure"), ...keep, finding("VanillaIceCube/agent-hub"),
  ] }, metadata] }));
  const bash = process.platform === "win32" ? "C:/Program Files/Git/bin/bash.exe" : "bash";
  const run = spawnSync(bash, ["-e", "-c", filter.run], { encoding: "utf8",
    env: { ...process.env, ...filter.env, RUNNER_TEMP: temp.replaceAll("\\", "/") } });
  assert.equal(run.status, 0, run.stderr);
  assert.deepEqual(JSON.parse(fs.readFileSync(report)), { runs: [{ ...metadata, results: keep }, metadata] });
});

test("PR gates deliver independent results to the same three trusted reviewers", () => {
  assert.deepEqual(ci.on.pull_request.types, ["opened", "synchronize", "reopened", "ready_for_review"]);
  assert.deepEqual(ci.on.pull_request["branches-ignore"], ["env-prod"]);
  assert.deepEqual(Object.keys(ci.on), ["pull_request"]);
  const security = ["codeql", "dependency-vulnerability", ...(app ? ["dependency-malware"] : []), "secrets"];
  for (const [job, file] of [["lints", "gate-lint"], ["tests", "gate-test"]]) {
    assert.equal(ci.jobs[job].uses, app ? shared("infrastructure", file) : `./.github/workflows/${file}.yml`);
    assert.equal(ci.jobs[job].with.application, app);
  }
  for (const [id, file, name, needs, secrets] of [
    ["code-review", "review-code", "AI Code Review", [], ["OBI_WAN_OPENAI_API_KEY", "OBI_WAN_CODE_NOBI_PRIVATE_KEY"]],
    ["build-review", "review-build", "AI Build Sheriff Review", ["lints", "tests"], ["LINT_EASTWOOD_OPENAI_API_KEY", "LINT_EASTWOOD_PRIVATE_KEY"]],
    ["security-review", "review-security", "AI Security Review", security, ["ROBOCOP_OPENAI_API_KEY", "ROBOCOP_PRIVATE_KEY"]],
  ]) {
    const job = ci.jobs[id];
    assert.equal(job.uses, shared("agent-hub", file));
    assert.equal(job.name, name);
    assert.deepEqual(job.needs ?? [], needs);
    assert.equal(job.with.publish, true);
    assert.deepEqual(Object.keys(job.secrets).sort(), secrets.sort());
    for (const key of secrets) assert.equal(job.secrets[key], "${{ secrets." + key + " }}");
    const conditions = job.if.split("&&").map(part => part.trim());
    assert.ok(conditions.includes("github.event.pull_request.head.repo.full_name == github.repository"));
    assert.equal(conditions.includes("always()"), needs.length > 0);
    assert.ok(conditions.every(part => ["always()", "github.event_name == 'pull_request'",
      "github.event.pull_request.head.repo.full_name == github.repository"].includes(part)));
    assert.ok(!job["continue-on-error"]);
  }
  assert.equal(ci.jobs["security-review"].with.dependency_vulnerability_report,
    "${{ needs.dependency-vulnerability.outputs.vulnerability_report }}");
  if (app) {
    for (const [id, gate] of Object.entries({
      codeql: "alert-codeql", secrets: "gate-secrets",
      "dependency-vulnerability": "gate-vulnerability", "dependency-malware": "gate-malware",
    })) assert.equal(ci.jobs[id].uses, shared("infrastructure", gate));
    assert.equal(ci.jobs["security-review"].with.dependency_malware_report,
      "${{ needs.dependency-malware.outputs.malware_report }}");
  }
});

test("branch rule verification uses the provider revision and reports failures to the required check", () => {
  const gate = path.resolve(__dirname, "../../workflows/gate-branch-rules.yml");
  const [checkout, probe] = YAML.parse(fs.readFileSync(gate, "utf8")).jobs.verify.steps;
  assert.equal(checkout.with.repository, "${{ job.workflow_repository }}");
  assert.equal(checkout.with.ref, "${{ job.workflow_sha }}");
  assert.equal(checkout.with["persist-credentials"], false);
  assert.equal(probe.if, "github.event.pull_request.head.repo.full_name == github.repository");
  assert.equal(probe.uses, "./.github/actions/verify-branch-rules");
  if (!app) return;

  const gateCaller = ci.jobs["branch-rules"];
  const required = ci.jobs["auto-merge"];
  assert.equal(gateCaller.uses, shared("infrastructure", "gate-branch-rules"));
  assert.equal(gateCaller.if, "always()");
  assert.equal(required.name, "Auto Merge");
  assert.equal(required.needs, "branch-rules");
  assert.equal(required.if, "always()");
  const [report] = required.steps;
  assert.equal(report.env.RESULT, "${{ needs.branch-rules.result }}");
  const shell = process.platform === "win32" ? "C:/Program Files/Git/bin/bash.exe" : "bash";
  for (const result of ["success", "failure", "cancelled", "skipped", ""]) {
    const run = spawnSync(shell, ["-c", report.run], { env: { ...process.env, RESULT: result } });
    assert.equal(run.status, result === "success" ? 0 : 1);
  }
});

test("CodeQL can scan and update tickets independently, with a scan-only manual option", () => {
  const alerts = workflow("alert-codeql");
  const { aggregate } = alerts.jobs;
  const scan = app ? alerts.jobs.scan : alerts.jobs.changes;
  const manual = alerts.on.workflow_dispatch.inputs.scan_only;
  assert.equal(manual.type, "boolean");
  assert.equal(manual.default, false);
  assert.equal(scan.if, "github.event_name == 'schedule' || inputs.scan_only");
  assert.equal(scan.needs, undefined);
  assert.equal(ci.jobs.codeql.name, "CodeQL");
  assert.equal(ci.jobs.codeql.with.scan_only, true);
  assert.equal(ci.jobs.codeql.uses, app ? shared("infrastructure", "alert-codeql") : "./.github/workflows/alert-codeql.yml");
  if (app) {
    assert.equal(scan.uses, ci.jobs.codeql.uses);
    assert.equal(scan.with.scan_only, true);
    assert.equal(aggregate.if, "github.event_name == 'schedule' || !inputs.scan_only");
  } else {
    assert.equal(alerts.on.workflow_call.inputs.scan_only.default, true);
    assert.equal(aggregate.if, "(github.event_name == 'schedule' || github.event_name == 'workflow_dispatch') && !inputs.scan_only");
  }
});

test("all three feeds update tickets independently at midnight Pacific or on manual dispatch", () => {
  for (const feed of ["codeql", "malware", "vulnerability"]) {
    const alerts = workflow("alert-" + feed);
    const job = alerts.jobs.aggregate;
    const events = !app && feed === "codeql" ? ["schedule", "workflow_call", "workflow_dispatch"] : ["schedule", "workflow_dispatch"];
    assert.deepEqual(Object.keys(alerts.on).sort(), events);
    assert.deepEqual(alerts.on.schedule, [{ cron: "0 0 * * *", timezone: "America/Los_Angeles" }]);
    assert.equal(job.needs, undefined);
    if (feed !== "codeql") assert.equal(job.if, undefined);
    assert.equal(job.uses, shared("agent-hub", "triage-security"));
    assert.equal(job.with.feed, feed);
    assert.deepEqual(job.permissions, { contents: "read" });
    assert.equal(job.with.publish, true);
  }
});
