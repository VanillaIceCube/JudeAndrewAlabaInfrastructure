// Require successful gates and the reviewer outcomes expected for this PR.
const fs = require("node:fs");

const gates = ["lints", "tests", "codeql", "dependency-vulnerability", "secrets"];
const reviews = ["code-review", "build-review", "security-review"];

function reviewsApplicable(event, repository) {
  return Boolean(repository && event.pull_request?.head?.repo?.full_name === repository);
}

function failures(results, applicable) {
  const problems = [];
  for (const name of [...gates, ...reviews].sort()) {
    const expected = reviews.includes(name) && !applicable ? "skipped" : "success";
    const actual = results[name]?.result ?? "missing";
    if (actual !== expected) problems.push(name + ": " + actual + " (expected " + expected + ")");
  }
  return problems;
}

module.exports = { reviewsApplicable, failures };
if (require.main === module) {
  const event = JSON.parse(fs.readFileSync(process.env.GITHUB_EVENT_PATH, "utf8"));
  const applicable = reviewsApplicable(event, process.env.GITHUB_REPOSITORY);
  const problems = failures(JSON.parse(process.env.RESULTS), applicable);
  if (problems.length) {
    console.error(problems.join("\n"));
    process.exitCode = 1;
  } else {
    console.log("All independent gates and applicable reviews passed.");
  }
}
