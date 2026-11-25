"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const YAML = require("yaml");

const actionDirectory = path.resolve(__dirname, '../actions/setup-uv');
const actionSteps = YAML.parse(fs.readFileSync(path.join(actionDirectory, 'action.yml'), 'utf8')).runs.steps;

test('uv bootstrap pins the reviewed runner, wheel and pip flags and propagates pip failures', () => {
  const step = actionSteps.find(step => step.name === 'Install uv');
  assert.equal(step.run.trim(), 'node "$GITHUB_ACTION_PATH/setup-uv.js"');
  const { install } = require("../actions/setup-uv/setup-uv");
  const env = { RUNNER_OS: 'Linux', RUNNER_ARCH: 'X64' };
  for (const status of [0, 1]) {
    const result = install(env, (program, args, options) => {
      assert.equal(program, 'python');
      assert.deepEqual(args.slice(0, 4), ['-m', 'pip', '--isolated', 'install']);
      for (const flag of ['--no-cache-dir', '--force-reinstall', '--no-deps', '--only-binary=:all:', '--require-hashes']) assert.ok(args.includes(flag), flag);
      assert.equal(args[args.indexOf('--index-url') + 1], 'https://pypi.org/simple');
      assert.equal(args[args.indexOf('--requirement') + 1], '/dev/stdin');
      assert.match(options.input, /^uv==0\.13\.8 --hash=sha256:[a-f0-9]{64}\n$/);
      return { status };
    });
    assert.equal(result, status);
  }
  for (const target of [{ RUNNER_OS: 'Windows' }, { RUNNER_ARCH: 'ARM64' }]) {
    assert.throws(() => install({ ...env, ...target }, assert.fail), /reviewed Linux X64 wheel/);
  }
});
