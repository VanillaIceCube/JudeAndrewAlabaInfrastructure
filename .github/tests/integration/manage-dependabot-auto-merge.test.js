"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const YAML = require("yaml");
const {
  enableAutoMerge,
  startPolicy,
  checkAndEnable,
  finishPolicy,
  independentChecks,
  policyContext,
  reviewers,
  resolveRun,
  verifyAlerts,
  verifyReviews,
} = require("../../scripts/manage-dependabot-auto-merge");

function harness() {
  const h = {
    pr: {
      number: 1, node_id: "PR_1", state: "open", merged: false, draft: false,
      user: { login: "dependabot[bot]", type: "Bot" },
      head: { sha: "a".repeat(40), repo: { full_name: "owner/infrastructure" } },
      base: { ref: "main", repo: { full_name: "owner/infrastructure" } },
      mergeable: true, mergeable_state: "blocked", auto_merge: null,
    },
    metadata: { updateType: "version-update:semver-patch" },
    calls: [],
    policyCheckId: 10000,
  };
  h.expected = { number: h.pr.number, nodeId: h.pr.node_id, headSha: h.pr.head.sha };
  h.context = { eventName: "workflow_run", repo: { owner: "owner", repo: "infrastructure" }, payload: { workflow_run: { id: 8, head_sha: h.expected.headSha } } };
  const names = independentChecks;
  h.rules = [{ type: "pull_request" }, { type: "required_status_checks", parameters: { required_status_checks: [{ context: "Required CI", integration_id: 15368 }, { context: policyContext, integration_id: 15368 }] } }];
  h.checks = names.map((name, id) => ({ id, name, status: "completed", conclusion: "success", app: { id: 15368, slug: "github-actions" } }));
  h.checks.push({ id: h.policyCheckId, name: policyContext, status: "in_progress", conclusion: null, app: { id: 15368, slug: "github-actions" } });
  h.reviews = Object.keys(reviewers).map((login, id) => ({ id, user: { login, type: "Bot" }, state: "APPROVED", commit_id: h.pr.head.sha }));
  h.run = { id: 8, workflow_id: 7, event: "pull_request", conclusion: "success", head_repository: { full_name: "owner/infrastructure" }, head_sha: h.pr.head.sha };
  h.github = {
    rest: {
      pulls: { get: async () => ({ data: structuredClone(h.pr) }), listReviews() {}, listFiles() {}, listCommits() {} },
      dependabot: { listAlertsForRepo() {} },
      repos: { getBranchRules() {}, listPullRequestsAssociatedWithCommit() {} },
      checks: { listForRef() {} },
      actions: { getWorkflowRun: async () => ({ data: h.run }), getWorkflow: async () => ({ data: { id: 7 } }) },
    },
    async paginate(method, params) {
      assert.equal(params.per_page, 100);
      if (method === h.github.rest.pulls.listReviews) return h.reviews;
      if (method === h.github.rest.pulls.listFiles) return h.files || [];
      if (method === h.github.rest.pulls.listCommits) return h.commits || [{ sha: h.pr.head.sha, author: { login: "dependabot[bot]" }, commit: { verification: { verified: true }, message: `Update\n\n---\n${JSON.stringify({ "updated-dependencies": h.dependencies || [{ "dependency-name": "example", "update-type": h.metadata.updateType }] })}\n...\n` } }];
      if (method === h.github.rest.dependabot.listAlertsForRepo) return h.alerts || [];
      if (method === h.github.rest.repos.getBranchRules) return h.rules;
      if (method === h.github.rest.repos.listPullRequestsAssociatedWithCommit) return [h.pr];
      assert.equal(params.ref, h.expected.headSha);
      return h.checks;
    },
    async graphql(query, variables) {
      h.calls.push({ query, variables });
      h.pr.auto_merge = { merge_method: "merge" };
    },
  };
  h.core = { info() {} };
  h.sleep = async () => {};
  h.enable = () => enableAutoMerge(h);
  h.resolve = () => resolveRun({ ...h, context: { ...h.context, eventName: "workflow_run", payload: { workflow_run: { id: 8, head_sha: "a".repeat(40) } } } });
  return h;
}

test("enables only native auto-merge with an atomic expected head; repeats are idempotent", async () => {
  const h = harness();
  assert.equal(await h.enable(), "enabled");
  assert.equal(await h.enable(), "already-enabled");
  assert.equal(h.calls.length, 1);
  assert.match(h.calls[0].query, /enablePullRequestAutoMerge/);
  assert.match(h.calls[0].query, /expectedHeadOid: \$head/);
  assert.equal(h.calls[0].variables.head, h.pr.head.sha);
});

test("only a same-repository Dependabot PR is eligible when opening its exact-head policy", async () => {
  for (const change of ["dependabot", "human", "fork", "production", "closed-after-listing"]) {
    const h = harness();
    if (change === "human") h.pr.user = { login: "maintainer", type: "User" };
    if (change === "fork") h.pr.head.repo.full_name = h.run.head_repository.full_name = "fork/app";
    if (change === "production") h.pr.base.ref = "env-prod";
    if (change === "closed-after-listing") h.github.rest.pulls.get = async () => ({ data: { ...h.pr, state: "closed" } });
    const outputs = {};
    h.core.setOutput = (name, value) => { outputs[name] = value; };
    h.github.rest.checks.create = async request => {
      assert.equal(request.head_sha, h.expected.headSha);
      assert.equal(request.status, "in_progress");
      return { data: { id: h.policyCheckId } };
    };
    await startPolicy(h);
    if (change === "production" || change === "closed-after-listing") assert.deepEqual(outputs, {});
    else {
      assert.equal(outputs.eligible, change === "dependabot");
      assert.equal(outputs.policy_id, h.policyCheckId);
      assert.equal(outputs.node_id, h.pr.node_id);
    }
    assert.equal(h.calls.length, 0);
  }
});

test("the workflow enable step uses its verified PR identity and the configured reviewer logins", async () => {
  const h = harness();
  const [code, build, security] = Object.keys(reviewers);
  const handoff = {
    POLICY_CHECK_ID: String(h.policyCheckId), HEAD_SHA: h.pr.head.sha, PR_NUMBER: String(h.pr.number), PR_NODE_ID: h.pr.node_id,
    OBI_WAN_REVIEWER_LOGIN: code, LINT_EASTWOOD_REVIEWER_LOGIN: build, ROBOCOP_REVIEWER_LOGIN: security,
  };
  const saved = Object.fromEntries(Object.keys(handoff).map(key => [key, process.env[key]]));
  try {
    Object.assign(process.env, handoff);
    assert.equal(await checkAndEnable(h), "enabled");
    process.env.PR_NODE_ID = "different-PR";
    await assert.rejects(checkAndEnable(h), /identity or head changed/);
    assert.equal(h.calls.length, 1);
  } finally {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
});

test("inapplicable events and stale handoffs cannot authorize a merge", async () => {
  for (const change of [
    h => { h.pr.user.login = "human"; }, h => { h.pr.head.repo.full_name = "fork/app"; },
    h => { h.pr.base.ref = "env-prod"; }, h => { h.context.eventName = "push"; },
    h => { h.context.payload = {}; }, h => { h.expected.nodeId = "PR_other"; },
  ]) {
    const h = harness(); change(h);
    await assert.rejects(h.enable(), /identity|head changed/);
    assert.equal(h.calls.length, 0);
  }
});

test("successful, failed and cancelled jobs conclude the original policy check", async () => {
  const original = { ...process.env };
  try {
    for (const status of ["success", "failure", "cancelled"]) {
      process.env.JOB_STATUS = status;
      process.env.POLICY_CHECK_ID = "42";
      let check;
      const github = { rest: { checks: { update: async input => { check = input; } } } };
      await finishPolicy({ github, context: { repo: { owner: "example", repo: "infrastructure" } } });
      assert.equal(check.check_run_id, 42);
      assert.equal(check.conclusion, status === "success" ? "success" : "failure");
    }
  } finally {
    for (const key of ["JOB_STATUS", "POLICY_CHECK_ID"]) {
      if (original[key] === undefined) delete process.env[key];
      else process.env[key] = original[key];
    }
  }
});

test("missing metadata fails; ineligible updates skip without mutation", async () => {
  const h = harness(); h.metadata = {};
  await assert.rejects(h.enable(), /metadata is missing/);
  h.metadata.updateType = "version-update:semver-major";
  assert.equal(await h.enable(), "ineligible");
  assert.equal(h.calls.length, 0);
});

test("failed, missing, pending, cancelled and skipped reviewers cannot enable auto-merge", async () => {
  for (const conclusion of ["failure", "cancelled", "skipped", "neutral", null]) {
    const h = harness(); h.checks.find((check) => check.name === Object.values(reviewers)[0]).conclusion = conclusion;
    await assert.rejects(h.enable(), /Required check/);
    assert.equal(h.calls.length, 0);
  }
  const h = harness(); h.checks = h.checks.filter((check) => check.name !== Object.values(reviewers)[0]);
  await assert.rejects(h.enable(), /Required check/);
});

test("all required gates, integration identity, and protected-branch rules are checked", async () => {
  for (const mutate of [
    (h) => { h.checks[0].conclusion = "failure"; },
    (h) => { h.checks[0].status = "in_progress"; },
    (h) => { h.checks[0].app.slug = "other-app"; },
    (h) => { h.rules = []; },
    (h) => { h.rules[1].parameters.required_status_checks.pop(); },
    (h) => { h.rules[1].parameters.required_status_checks[0].integration_id = 9; },
  ]) {
    const h = harness(); mutate(h);
    await assert.rejects(h.enable());
    assert.equal(h.calls.length, 0);
  }
});

test("latest check rerun supersedes an earlier failure, but not a newer pending rerun", async () => {
  const h = harness();
  h.checks.push({ ...h.checks[0], id: 100, conclusion: "failure" });
  await assert.rejects(h.enable(), /Required check/);
  h.checks.push({ ...h.checks[0], id: 101 });
  assert.equal(await h.enable(), "enabled");
  h.checks.push({ ...h.checks[0], id: 102, status: "queued", conclusion: null });
  await assert.rejects(h.enable(), /Required check/);
});

test("a new external required provider holds auto-merge for an owner decision", async () => {
  const h = harness();
  const context = "External policy";
  h.rules[1].parameters.required_status_checks.push({ context, integration_id: 67890 });
  h.checks.push({ id: 2000, name: context, status: "completed", conclusion: "success",
    app: { id: 67890, slug: "external-provider" } });
  await assert.rejects(h.enable(), /Manual merge required: External policy/);
  assert.equal(h.calls.length, 0);
});

test("CodeQL skips follow Infrastructure path filters and consider both sides of a rename", async () => {
  const python = "CodeQL / Analyze Python";
  const h = harness();
  h.checks.find(check => check.name === python).conclusion = "skipped";
  h.files = [];
  assert.equal(await h.enable(), "enabled");
  h.files = [{ filename: "README.md" }];
  assert.equal(await h.enable(), "already-enabled");
  h.files = [{ filename: "README.md", previous_filename: "service.py" }];
  await assert.rejects(h.enable(), /Required check/);
});

test("eligible Dependabot merges require the aggregate, independent checks and three reviewer jobs", async () => {
  for (const name of independentChecks) {
    const h = harness();
    h.checks = h.checks.filter(check => check.name !== name);
    await assert.rejects(h.enable(), /Required check/, name);
    assert.equal(h.calls.length, 0);
  }
  const h = harness();
  h.rules[1].parameters.required_status_checks.shift();
  await assert.rejects(h.enable(), /Required CI must be required/);
  assert.equal(h.calls.length, 0);
});

test("approvals must come from every persona on this head; comments do not clear blockers", async () => {
  for (const mutate of [
    (h) => { h.reviews.pop(); },
    (h) => { h.reviews[0].state = "COMMENTED"; },
    (h) => { h.reviews[0].commit_id = "old"; },
    (h) => { h.reviews[0].user.type = "User"; },
    (h) => { h.reviews.push({ id: 100, user: { login: "human" }, state: "CHANGES_REQUESTED" }); },
  ]) {
    const h = harness(); mutate(h);
    await assert.rejects(h.enable(), /approval|requesting changes/);
    assert.equal(h.calls.length, 0);
  }
  const h = harness();
  h.reviews.push({ id: 100, user: { login: "human" }, state: "CHANGES_REQUESTED" });
  h.reviews.push({ id: 101, user: { login: "human" }, state: "COMMENTED" });
  assert.throws(() => verifyReviews(h.reviews, h.pr.head.sha), /requesting changes/);
});

test("unstable, conflicting, unknown and changed heads cannot merge", async () => {
  for (const state of ["unstable", "dirty", "unknown", "behind"]) {
    const h = harness(); h.pr.mergeable_state = state;
    await assert.rejects(h.enable(), /not stable/);
    assert.equal(h.calls.length, 0);
  }
  const h = harness(); h.pr.head.sha = "new";
  await assert.rejects(h.enable(), /head changed/);
  for (const field of ["draft", "merged"]) {
    const h = harness(); h.pr[field] = true;
    assert.equal(await h.enable(), "inactive");
  }
});

test("mutation races are idempotent only when the same head is already enabled", async () => {
  const h = harness();
  h.github.graphql = async () => { h.pr.auto_merge = {}; throw new Error("concurrent event"); };
  assert.equal(await h.enable(), "already-enabled");
  const failed = harness();
  failed.github.graphql = async () => { throw new Error("permission denied"); };
  await assert.rejects(failed.enable(), /permission denied/);
  const moved = harness();
  moved.github.graphql = async () => { moved.pr.head.sha = "new"; moved.pr.auto_merge = {}; throw new Error("head moved"); };
  await assert.rejects(moved.enable(), /head moved/);
});

test("transient unknown mergeability settles with bounded polling and head revalidation", async () => {
  const h = harness();
  h.pr.mergeable = null; h.pr.mergeable_state = "unknown";
  let retries = 0;
  h.sleep = async (ms) => {
    assert.equal(ms, 2000);
    retries += 1;
    h.pr.mergeable = true; h.pr.mergeable_state = "blocked";
  };
  assert.equal(await h.enable(), "enabled");
  assert.equal(retries, 1);
  const stuck = harness(); stuck.pr.mergeable = null; stuck.pr.mergeable_state = "unknown";
  let waits = 0; stuck.sleep = async () => { waits += 1; };
  await assert.rejects(stuck.enable(), /not stable/);
  assert.equal(waits, 5);
  assert.equal(stuck.calls.length, 0);
  const moved = harness(); moved.pr.mergeable = null;
  moved.sleep = async () => { moved.pr.head.sha = "new"; };
  await assert.rejects(moved.enable(), /head changed/);
});

test("follow-up validates authoritative CI identity, result and head, independent of rerun actor", async () => {
  const h = harness();
  assert.equal((await h.resolve()).number, 1);
  for (const patch of [
    { workflow_id: 99 }, { event: "push" }, { conclusion: "failure" },
    { conclusion: "cancelled" }, { head_sha: "new" },
  ]) {
    const h = harness(); Object.assign(h.run, patch);
    await assert.rejects(h.resolve(), /not successful/);
  }
  const human = harness(); human.pr.user.login = "human";
  assert.equal((await human.resolve()).user.login, "human");
  const fork = harness(); fork.pr.head.repo.full_name = "fork/app";
  fork.run.head_repository.full_name = "fork/app";
  assert.equal((await fork.resolve()).head.repo.full_name, "fork/app");
});

test("every group member needs explicit patch/minor metadata", async () => {
  const h = harness();
  h.dependencies = [{ "dependency-name": "one", "update-type": "version-update:semver-patch" }, { "dependency-name": "two", "update-type": "version-update:semver-major" }];
  assert.equal(await h.enable(), "ineligible");
  assert.equal(h.calls.length, 0);
  h.dependencies[1]["update-type"] = undefined;
  await assert.rejects(h.enable(), /metadata is missing/);
});

test("signed metadata is bound to the only PR commit and exact current head", async () => {
  for (const commits of [[], [{ sha: "other", author: { login: "dependabot[bot]" }, commit: { verification: { verified: true } } }],
    [{ sha: "a".repeat(40), author: { login: "human" }, commit: { verification: { verified: true } } }],
    [{ sha: "a".repeat(40), author: { login: "dependabot[bot]" }, commit: { verification: { verified: false } } }],
    [{}, {}]]) {
    const h = harness(); h.commits = commits;
    await assert.rejects(h.enable(), /exactly one verified Dependabot commit/);
    assert.equal(h.calls.length, 0);
  }
});

test("all open alerts across all group members enforce the CVSS ceiling", async () => {
  const dependencies = [{ dependencyName: "one" }, { dependencyName: "two" }];
  const alert = (name, state, score) => ({ state, dependency: { package: { name } }, security_advisory: { cvss: { score } } });
  for (const score of [0, 6.9]) verifyAlerts(dependencies, [alert("one", "open", score)]);
  for (const score of [7, -1, NaN, "6.9garbage", null, Infinity]) {
    assert.throws(() => verifyAlerts(dependencies, [alert("one", "open", score)]), /CVSS/);
  }
  verifyAlerts(dependencies, [alert("one", "dismissed", 9.8), alert("two", "fixed", 9.8)]);
  assert.throws(() => verifyAlerts(dependencies, [alert("one", "open", 1), alert("two", "open", 9.8)]), /CVSS/);
  assert.throws(() => verifyAlerts(dependencies, [alert("two", "open", null)]), /CVSS/);
  assert.throws(() => verifyAlerts([{ dependencyName: "github/codeql-action/init" }], [alert("github/codeql-action", "open", 9.8)]), /CVSS/);
  const h = harness(); h.alerts = Array.from({ length: 101 }, () => alert("other", "open", 1));
  h.alerts.push(alert("example", "open", 9.8));
  await assert.rejects(h.enable(), /CVSS/);
  assert.equal(h.calls.length, 0);
});

test("a required pending per-head policy holds native auto-merge through later pushes", async () => {
  const h = harness(); h.rules[1].parameters.required_status_checks.pop();
  await assert.rejects(h.enable(), /Policy must be required/);
  const changed = harness(); changed.checks.at(-1).id = 20000;
  await assert.rejects(changed.enable(), /Required check/);
  const clean = harness(); clean.pr.mergeable_state = "clean";
  await assert.rejects(clean.enable(), /not stable/);
});

test("a previous successful policy check cannot stand in for this run's pending check", async () => {
  const h = harness();
  const pending = h.checks.pop();
  h.checks.push({ ...pending, id: pending.id - 1, status: "completed", conclusion: "success" });
  let waits = 0;
  h.sleep = async () => { waits++; };
  await assert.rejects(h.enable(), /Required check/);
  assert.equal(waits, 5);
  assert.equal(h.calls.length, 0);

  h.sleep = async () => { h.checks.push(pending); };
  assert.equal(await h.enable(), "enabled");
});

test("policy check visibility is polled boundedly without trusting a stale head", async () => {
  const h = harness(); const paginate = h.github.paginate.bind(h.github);
  let reads = 0; let waits = 0;
  h.github.paginate = async (method, params) => {
    if (method === h.github.rest.checks.listForRef && reads++ === 0) return h.checks.filter((check) => check.name !== policyContext);
    return paginate(method, params);
  };
  h.sleep = async () => { waits += 1; };
  assert.equal(await h.enable(), "enabled");
  assert.equal(reads, 2); assert.equal(waits, 1);
  const stuck = harness(); stuck.checks = stuck.checks.filter((check) => check.name !== policyContext);
  let stuckWaits = 0; stuck.sleep = async () => { stuckWaits += 1; };
  await assert.rejects(stuck.enable(), /Required check/);
  assert.equal(stuckWaits, 5); assert.equal(stuck.calls.length, 0);
  const moved = harness(); moved.checks = moved.checks.filter((check) => check.name !== policyContext);
  moved.sleep = async () => { moved.pr.head.sha = "new"; };
  await assert.rejects(moved.enable(), /head changed/);
});

test("generated apps can configure three distinct reviewer bot identities", () => {
  const head = "head";
  const logins = ["app-code[bot]", "app-build[bot]", "app-security[bot]"];
  verifyReviews(logins.map((login, id) => ({ id, state: "APPROVED", commit_id: head, user: { login, type: "Bot" } })), head, logins);
  assert.throws(() => verifyReviews([], head, ["same[bot]", "same[bot]", "other[bot]"]), /Three distinct/);
});

test("the policy checks the job contexts emitted by every Required CI dependency", () => {
  const root = path.resolve(__dirname, "../../..");
  const readJobs = relative => YAML.parse(fs.readFileSync(path.join(root, relative), "utf8")).jobs;
  const jobs = readJobs(".github/workflows/ci-orchestrator.yml");
  const contexts = [jobs.result.name];
  for (const dependency of jobs.result.needs) {
    const caller = jobs[dependency];
    if (caller.uses.startsWith("VanillaIceCube/agent-hub/")) {
      const review = Object.values(reviewers).find(name => name.startsWith(caller.name + " / "));
      assert.ok(review, "Missing required reviewer for " + caller.name);
      contexts.push(review);
      continue;
    }
    const children = readJobs(caller.uses);
    if (dependency === "lints" || dependency === "tests") {
      assert.equal(caller.with.application, false);
      assert.equal(children.changes.if, "inputs.application");
    }
    for (const [id, job] of Object.entries(children)) {
      // The application path detector and its dependents do not run on an Infrastructure PR.
      if (caller.with?.application === false &&
          (job.if === "inputs.application" || job.if === "always() && inputs.application" || job.needs === "changes")) continue;
      if (dependency === "codeql" && id === "aggregate") {
        assert.equal(caller.with.scan_only, true);
        assert.equal(job.if, "(github.event_name == 'schedule' || github.event_name == 'workflow_dispatch') && !inputs.scan_only");
        continue;
      }
      // Infrastructure uses the default CodeQL job names. AgentHub selects the tree-based names.
      const defaultName = job.name?.match(/\|\| '([^']+)' \}\}$/)?.[1];
      contexts.push(caller.name + " / " + (defaultName ?? job.name ?? id));
    }
  }
  assert.deepEqual([...independentChecks].sort(), contexts.sort());
});

test("privileged workflow uses only main code and verified metadata, with no immediate merge path", () => {
  const workflows = path.resolve(__dirname, "../../workflows");
  const workflow = fs.readFileSync(path.join(workflows, "ci-auto-merge.yml"), "utf8");
  assert.match(workflow, /workflow_run:/);
  assert.match(workflow, /workflows: \[CI\]/);
  const [policy, subject] = YAML.parse(workflow).jobs["dependabot-auto-merge"].steps;
  assert.equal(policy.with.repository, "${{ job.workflow_repository }}");
  assert.equal(policy.with.ref, "${{ job.workflow_sha }}");
  assert.equal(subject.with.ref, "${{ github.sha }}");
  assert.equal(subject.with.path, "subject");
  assert.match(workflow, /Compare caller workflow write grants\s+if: steps\.pr\.outputs\.policy_id != ''/);
  assert.match(workflow, /persist-credentials: false/);
  assert.match(workflow, /\.checkAndEnable\(\{ github, context, core \}\)/);
  assert.doesNotMatch(workflow, /pull_request_target|workflow_dispatch|secrets\.|download-artifact|actions\/cache|skip-verification|skip-commit-verification/);
  for (const pin of workflow.matchAll(/uses: ([^\s]+)@([^\s]+)/g)) assert.match(pin[2], /^[a-f0-9]{40}$/);
  const source = fs.readFileSync(require.resolve("../../scripts/manage-dependabot-auto-merge"), "utf8");
  assert.doesNotMatch(source, /pulls\.merge|mergePullRequest\(/);
  const orchestrator = fs.readFileSync(path.join(workflows, "ci-orchestrator.yml"), "utf8");
  assert.doesNotMatch(orchestrator, /uses: .*ci-auto-merge.yml/);
  assert.match(orchestrator, /Verify branch rules are readable with the workflow token/);
  assert.ok(orchestrator.includes("uses: ./.github/actions/verify-branch-rules"));
  const probe = fs.readFileSync(require.resolve("../../actions/verify-branch-rules/verify-branch-rules"), "utf8");
  assert.match(probe, /expectedHeadOid/);
  assert.match(orchestrator, /needs: \[lints, tests, codeql, dependency-vulnerability, secrets, code-review, build-review, security-review\]/);
  assert.match(workflow, /vulnerability-alerts: read/);
  assert.match(workflow, /checks: write/);
  assert.match(source, /github.rest.checks.create/);
  assert.match(source, /github.rest.checks.update/);
  assert.match(workflow, /\.startPolicy\(\{ github, context, core \}\)/);
  assert.match(workflow, /Validate this head and enable native protected-branch auto-merge\s+if: steps\.pr\.outputs\.eligible == 'true'/);
  assert.match(workflow, /if: always\(\) && steps\.pr\.outputs\.policy_id != ''/);
  assert.match(workflow, /\.finishPolicy\(\{ github, context \}\)/);
  assert.doesNotMatch(workflow, /GITHUB_EVENT_PATH:/);
});

test("SHA-only signed Action metadata takes a reviewed manual path without semver guessing", async () => {
  const h = harness();
  h.dependencies = [{ "dependency-name": "dorny/paths-filter", "dependency-version": "f3360c560367c9daf72b88c0e6164162034c5721", "dependency-type": "direct:production" }];
  h.files = [{ filename: ".github/workflows/gate-test.yml" }];
  assert.equal(await h.enable(), "ineligible");
  assert.equal(h.calls.length, 0);
  h.reviews.pop();
  await assert.rejects(h.enable(), /approval/);
  h.reviews = harness().reviews;
  h.files.push({ filename: "frontend/package.json" });
  await assert.rejects(h.enable(), /exclusively GitHub Actions/);
  h.files = [{ filename: ".github/workflows/gate-test.yml" }];
  h.dependencies.push({ "dependency-name": "other" });
  await assert.rejects(h.enable(), /metadata is missing/);
});

test("inconsistent success/in-progress checks wait for actual completion, boundedly", async () => {
  const h = harness();
  const detector = h.checks.find(check => check.name === "Tests / validate");
  detector.status = "in_progress";
  detector.completed_at = "2026-11-05T00:06:10Z";
  let waits = 0;
  h.sleep = async () => { waits++; detector.status = "completed"; };
  assert.equal(await h.enable(), "enabled");
  assert.equal(waits, 1);
  const stuck = harness();
  Object.assign(stuck.checks[2], { status: "in_progress", conclusion: "success", completed_at: detector.completed_at });
  let attempts = 0;
  stuck.sleep = async () => { attempts++; };
  await assert.rejects(stuck.enable(), /Required check.*in_progress/);
  assert.equal(attempts, 5);
  assert.equal(stuck.calls.length, 0);
});

test("delayed checks cannot authorize failed or changed heads", async () => {
  for (const state of ["failure", "skipped", "cancelled"]) {
    const h = harness(); h.checks[0].conclusion = state;
    let waits = 0; h.sleep = async () => { waits++; };
    await assert.rejects(h.enable(), /Required check/);
    assert.equal(waits, 0); assert.equal(h.calls.length, 0);
  }
  const h = harness(); h.checks[0].status = "queued";
  h.sleep = async () => { h.pr.head.sha = "new"; };
  await assert.rejects(h.enable(), /head changed/);
  assert.equal(h.calls.length, 0);
});

test("application policy requires each native reviewer check and honors the matching app path filters", async () => {
  function appHarness() {
    const h = harness();
    h.pr.head.repo.full_name = h.pr.base.repo.full_name = "owner/notoli";
    h.context.repo.repo = "notoli";
    const names = ["Lints / Detect Changes", "Lints / Lint Results", "Tests / Detect Changes",
      "Tests / Test Results", "CodeQL / Detect CodeQL Scope", "Vulnerability / Vulnerability", "Malware / Malware",
      "Auto Merge", "Secret scan / Gitleaks", "Lints / Lint Backend (Ruff)", ...Object.values(reviewers)];
    h.rules[1].parameters.required_status_checks = [...names.map(context => ({ context })),
      { context: policyContext, integration_id: 15368 }];
    h.checks = [...h.checks.filter(check => check.name === policyContext), ...names.map((name, id) => ({
      id, name, status: "completed", conclusion: "success", app: { id: 15368, slug: "github-actions" },
    }))];
    h.checks.find(check => check.name === "Lints / Lint Backend (Ruff)").conclusion = "skipped";
    return h;
  }
  const allowed = appHarness();
  allowed.files = [{ filename: "README.md" }];
  await enableAutoMerge(allowed);
  for (const filename of ["backend/uv.lock", ".github/workflows/ci-orchestrator.yml"]) {
    const changed = appHarness();
    changed.files = [{ filename }];
    await assert.rejects(enableAutoMerge(changed), /Required check is not passing/);
  }
  const missing = appHarness();
  missing.rules[1].parameters.required_status_checks = missing.rules[1].parameters.required_status_checks
    .filter(check => check.context !== Object.values(reviewers)[0]);
  await assert.rejects(enableAutoMerge(missing), /Reviewer is not required/);
});
