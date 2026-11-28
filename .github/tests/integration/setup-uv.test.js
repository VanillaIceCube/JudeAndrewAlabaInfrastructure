"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const YAML = require("yaml");

const actionDirectory = path.resolve(__dirname, '../../actions/setup-uv');
const actionSteps = YAML.parse(fs.readFileSync(path.join(actionDirectory, 'action.yml'), 'utf8')).runs.steps;

test('uv bootstrap pins the reviewed runner, wheel and pip flags and propagates pip failures', () => {
  const step = actionSteps.find(step => step.name === 'Install uv');
  assert.equal(step.run.trim(), 'node "$GITHUB_ACTION_PATH/setup-uv.js"');
  const { install } = require("../../actions/setup-uv/setup-uv");
  const env = { RUNNER_OS: 'Linux', RUNNER_ARCH: 'X64' };
  for (const status of [0, 1]) {
    const result = install(env, (program, args, options) => {
      assert.equal(program, 'python');
      assert.deepEqual(args.slice(0, 4), ['-m', 'pip', '--isolated', 'install']);
      for (const flag of ['--no-cache-dir', '--force-reinstall', '--no-deps', '--only-binary=:all:', '--require-hashes']) assert.ok(args.includes(flag), flag);
      assert.ok(args.includes('--no-index'));
      assert.equal(options.stdio, 'inherit');
      const wheel = new URL(args.at(-1));
      assert.equal(wheel.origin, 'https://files.pythonhosted.org');
      assert.equal(path.posix.basename(wheel.pathname), 'uv-0.13.8-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl');
      assert.equal(wheel.hash, '#sha256=e18a57b8b352eb7c8feb317b9f6f533c8f0ad9673fd6cf34bbe3cf1a9f6a8984');
      return { status };
    });
    assert.equal(result, status);
  }
  for (const target of [{ RUNNER_OS: 'Windows' }, { RUNNER_ARCH: 'ARM64' }]) {
    assert.throws(() => install({ ...env, ...target }, assert.fail), /reviewed Linux X64 wheel/);
  }
});

test("application jobs install the correct locked dependency group from the caller", () => {
  for (const [workflow, job, onlyDev] of [
    ["gate-lint.yml", "lint-backend", "true"],
    ["gate-test.yml", "backend-tests", undefined],
    ["gate-test.yml", "automation-tests", "true"],
  ]) {
    const { jobs } = YAML.parse(fs.readFileSync(path.join(__dirname, "../../workflows", workflow), "utf8"));
    const step = jobs[job].steps.find(step => step.uses === "./.github/actions/setup-uv");
    assert.equal(step.with["project-directory"], "subject/backend");
    assert.equal(step.with["only-dev"], onlyDev);
  }
});
