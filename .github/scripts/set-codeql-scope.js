"use strict";

const fs = require("node:fs");
const { execFileSync } = require("node:child_process");

// AgentHub scans each language present, including on documentation-only changes.
function treeLanguages(revision) {
  const files = execFileSync("git", ["-C", "subject", "ls-tree", "-rz", "--name-only", revision],
    { encoding: "utf8", maxBuffer: 32 * 1024 * 1024 }).split("\0");
  return {
    python: files.some(file => file.endsWith(".py")),
    javascript: files.some(file => /\.(?:[cm]?[jt]s|[jt]sx)$/.test(file)),
    actions: true,
  };
}

function analysisScope(env) {
  if (env.LANGUAGES_IN_TREE === "true") return treeLanguages("HEAD");
  if (env.EVENT_NAME !== "pull_request") return { python: true, javascript: true, actions: true };
  const flags = [env.PYTHON_SCOPE, env.JAVASCRIPT_SCOPE, env.ACTIONS_SCOPE];
  if (!flags.every(value => value === "true" || value === "false")) {
    throw new Error("CodeQL scope output is missing or invalid");
  }
  const [python, javascript, actions] = flags.map(value => value === "true");
  return { python, javascript, actions: python || javascript || actions };
}

if (require.main === module) {
  const { python, javascript, actions } = analysisScope(process.env);
  fs.appendFileSync(process.env.GITHUB_OUTPUT, `scope_status=success\npython=${python}\njavascript=${javascript}\nactions=${actions}\n`);
}

module.exports = { treeLanguages };
