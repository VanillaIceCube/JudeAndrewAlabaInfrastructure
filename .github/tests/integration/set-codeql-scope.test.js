"use strict";

const assert = require("node:assert/strict");
const { execFileSync, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

test('workflow executes accurate PR scope and full push/schedule/manual scope', () => {
  const workflow = fs.readFileSync(path.join(__dirname, '../../workflows/alert-codeql.yml'), 'utf8').replaceAll('\r\n', '\n');
  assert.match(workflow, /- name: Set analysis scope[\s\S]*?run: node \.github\/scripts\/set-codeql-scope\.js/);
  const script = path.join(__dirname, '../../scripts/set-codeql-scope.js');
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'codeql-scope-'));
  try {
    for (const [event, python, javascript, actions, expected] of [
      ['pull_request', 'false', 'false', 'false', ['false', 'false', 'false']],
      ['pull_request', 'true', 'false', 'false', ['true', 'false', 'true']],
      ['pull_request', 'false', 'true', 'false', ['false', 'true', 'true']],
      ['pull_request', 'false', 'false', 'true', ['false', 'false', 'true']],
      ['push', '', '', '', ['true', 'true', 'true']],
      ['schedule', '', '', '', ['true', 'true', 'true']],
      ['workflow_dispatch', '', '', '', ['true', 'true', 'true']],
      ['pull_request', '', '', '', null],
    ]) {
      const output = path.join(directory, 'output');
      fs.writeFileSync(output, '');
      const result = spawnSync(process.execPath, [script], { env: { ...process.env, GITHUB_OUTPUT: output, EVENT_NAME: event, PYTHON_SCOPE: python, JAVASCRIPT_SCOPE: javascript, ACTIONS_SCOPE: actions }, encoding: 'utf8' });
      assert.equal(result.status, expected ? 0 : 1, result.stderr);
      const values = Object.fromEntries(fs.readFileSync(output, 'utf8').trim().split('\n').filter(Boolean).map((line) => line.split('=')));
      if (expected) {
        assert.equal(values.scope_status, 'success');
        assert.deepEqual([values.python, values.javascript, values.actions], expected);
      } else assert.equal(values.scope_status, undefined);
    }
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});

test("AgentHub selects languages from the named Git tree, ignoring untracked sources", t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "tree-languages-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const subject = path.join(root, "subject");
  fs.mkdirSync(subject);
  const git = (...args) => execFileSync("git", args, { cwd: subject, encoding: "utf8" }).trim();
  git("init", "--quiet");
  fs.writeFileSync(path.join(subject, "local.py"), "");
  const modulePath = require.resolve("../../scripts/set-codeql-scope");
  const inspect = revision => JSON.parse(execFileSync(process.execPath,
    ["-e", "console.log(JSON.stringify(require(process.argv[1]).treeLanguages(process.argv[2])))", modulePath, revision],
    { cwd: root, encoding: "utf8" }));
  const empty = git("write-tree");
  fs.writeFileSync(path.join(subject, "client.mts"), "");
  git("add", "client.mts");
  const js = git("write-tree");
  git("add", "local.py");
  assert.deepEqual(inspect(git("write-tree")), { python: true, javascript: true, actions: true });
  assert.deepEqual(inspect(js), { python: false, javascript: true, actions: true });
  assert.deepEqual(inspect(empty), { python: false, javascript: false, actions: true });
});
