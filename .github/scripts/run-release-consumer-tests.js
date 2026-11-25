const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync, spawnSync } = require('node:child_process');

const workspace = process.env.GITHUB_WORKSPACE;
// Exercise the candidate builder against the pinned application's policy and Compose file.
fs.copyFileSync(path.join(workspace, 'app-release/build_bundle.py'), 'deploy/production/build_bundle.py');
execFileSync('python3', ['deploy/production/build_bundle.py', '--check-parity', '--source-root', workspace, '--sync'],
  { stdio: 'inherit' });
const canonical = path.join(workspace, 'app-release/tests');
const consumer = path.resolve('deploy/tests');
const files = fs.readdirSync(canonical).filter(file => /^test_.*\.py$/.test(file)).sort();
assert.ok(files.length, 'Missing canonical release tests');
for (const file of files) {
  assert.ok(fs.readFileSync(path.join(canonical, file)).equals(fs.readFileSync(path.join(consumer, file))),
    'Consumer test differs from canonical source: ' + file);
}

const modules = files.map(file => path.basename(file, '.py'));
const result = spawnSync('python3', ['-m', 'unittest', '-v', ...modules], { cwd: consumer, stdio: 'inherit' });
if (result.error) throw result.error;
if (result.signal) console.error('Release tests stopped by ' + result.signal);
process.exitCode = result.status ?? 1;
