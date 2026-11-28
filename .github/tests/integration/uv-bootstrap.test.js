"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

function temporaryDirectory(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'composite-action-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}

test('the application Dockerfiles require hashed uv wheels and propagate pip failures', t => {
  const dir = temporaryDirectory(t);
  const stub = path.join(dir, 'python');
  fs.writeFileSync(stub, [
    '#!/usr/bin/env node',
    'const fs = require("node:fs");',
    'fs.writeFileSync("pip.args", process.argv.slice(2).join("\\n"));',
    'fs.writeFileSync("requirements", fs.readFileSync(0));',
    'process.exitCode = Number(process.env.PIP_EXIT);',
  ].join('\n'), { mode: 0o755 });
  const shell = process.platform === 'win32' ? 'C:/Program Files/Git/bin/bash.exe' : 'bash';
  let canonical;
  for (const name of ['Dockerfile', 'Dockerfile.hotswap']) {
    const text = fs.readFileSync(path.join('backend', 'docker', name), 'utf8').replace(/\\\r?\n/g, ' ');
    const install = text.split('\n').find(line => line.startsWith('RUN ') && line.includes('python -m pip'));
    assert.ok(install, name + ' must install uv with pip');
    const run = install.slice(4);
    if (canonical) assert.equal(run, canonical);
    canonical = run;
    for (const status of [0, 1]) {
      const result = spawnSync(shell, ['-c', run], {
        cwd: dir, encoding: 'utf8', timeout: 15000,
        env: { ...process.env, PATH: dir + path.delimiter + process.env.PATH, MSYS2_ARG_CONV_EXCL: '/dev/stdin', PIP_EXIT: String(status) },
      });
      assert.equal(result.status, status, result.stderr);
      const args = fs.readFileSync(path.join(dir, 'pip.args'), 'utf8').trim().split('\n');
      for (const flag of ['--isolated', '--no-cache-dir', '--force-reinstall', '--no-deps', '--only-binary=:all:', '--require-hashes']) assert.ok(args.includes(flag), flag);
      assert.equal(args[args.indexOf('--index-url') + 1], 'https://pypi.org/simple');
      assert.equal(args[args.indexOf('--requirement') + 1], '/dev/stdin');
      const requirements = fs.readFileSync(path.join(dir, 'requirements'), 'utf8');
      assert.match(requirements, /^uv==0\.13\.8(?:\s+--hash=sha256:[a-f0-9]{64}){7}\s*$/);
    }
  }
});
