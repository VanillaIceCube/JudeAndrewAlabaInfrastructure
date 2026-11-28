"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

test("audit accepts the actual GitHub check-runs API representation", () => {
  const {
    requiredReviewerContexts,
    reviewerGateProblems,
  } = require("../../scripts/validate-reviewer-gates");
  const captured = require("../fixtures/github-check-runs-passing.json");
  const ruleset = {
    enforcement: "active",
    rules: [
      {
        type: "required_status_checks",
        parameters: {
          required_status_checks: requiredReviewerContexts.map((context) => ({
            context,
          })),
        },
      },
    ],
  };
  assert.deepEqual(
    captured.check_runs.map((check) => check.name),
    requiredReviewerContexts,
  );
  assert.deepEqual(reviewerGateProblems(ruleset, captured.check_runs), []);
  const blocked = require("../fixtures/github-check-runs-failing.json");
  assert.deepEqual(reviewerGateProblems(ruleset, blocked.check_runs), [
    "Reviewer not successful: AI Build Sheriff Review / Lint Eastwood build sheriff review (completed/failure)",
    "Reviewer not successful: AI Security Review / RoboCop security review (completed/failure)",
  ]);
});

test("gate audit rejects missing, skipped, cancelled and failed reviewer results", () => {
  const {
    requiredReviewerContexts,
    reviewerGateProblems,
  } = require("../../scripts/validate-reviewer-gates");
  const ruleset = {
    enforcement: "active",
    rules: [
      {
        type: "required_status_checks",
        parameters: {
          required_status_checks: requiredReviewerContexts.map((context) => ({
            context,
          })),
        },
      },
    ],
  };
  const clean = requiredReviewerContexts.map((name, index) => ({
    id: index + 1,
    name,
    status: "completed",
    conclusion: "success",
  }));
  assert.deepEqual(reviewerGateProblems(ruleset, clean), []);
  assert.ok(
    reviewerGateProblems({ ...ruleset, enforcement: "disabled" }, clean).length,
  );
  assert.ok(reviewerGateProblems({ ...ruleset, rules: [] }, clean).length);
  for (const conclusion of [
    "failure",
    "cancelled",
    "skipped",
    "neutral",
    "timed_out",
    "action_required",
    "stale",
    null,
  ]) {
    assert.equal(
      reviewerGateProblems(ruleset, [
        ...clean,
        { ...clean[0], id: 10, conclusion },
      ]).length,
      1,
      String(conclusion),
    );
  }
  assert.equal(reviewerGateProblems(ruleset, clean.slice(1)).length, 1);
  assert.equal(
    reviewerGateProblems(ruleset, [
      ...clean,
      { ...clean[0], id: 10, status: "in_progress", conclusion: null },
    ]).length,
    1,
  );
  const failed = { ...clean[0], id: 10, conclusion: "failure" };
  const rerun = { ...failed, id: 11, conclusion: "success" };
  assert.equal(
    reviewerGateProblems(ruleset, [failed, ...clean.slice(1)]).length,
    1,
  );
  assert.deepEqual(
    reviewerGateProblems(ruleset, [failed, rerun, ...clean.slice(1)]),
    [],
    "A successful rerun supersedes the earlier failure",
  );
});
