const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync, spawn } = require('node:child_process');

async function main() {
  const workspace = process.env.GITHUB_WORKSPACE;
  execFileSync('python3', ['deploy/production/build_bundle.py', '--check-parity', '--source-root', workspace, '--sync'],
    { stdio: 'inherit' });
  const canonical = path.join(workspace, 'app-release/v1/tests');
  const consumer = path.resolve('deploy/tests');
  const files = fs.readdirSync(canonical).filter(file => /^test_.*\.py$/.test(file)).sort();
  assert.ok(files.length, 'Missing canonical release tests');
  for (const file of files) {
    assert.ok(fs.readFileSync(path.join(canonical, file)).equals(fs.readFileSync(path.join(consumer, file))),
      'Consumer test differs from canonical source: ' + file);
  }

  const log = fs.openSync(path.join(process.env.RUNNER_TEMP, 'release-tests.log'), 'w');
  try {
    const child = spawn('python3', ['-m', 'unittest', '-v', ...files.map(file => file.slice(0, -3))], { cwd: consumer });
    for (const stream of [child.stdout, child.stderr]) {
      stream.on('data', chunk => { process.stdout.write(chunk); fs.writeFileSync(log, chunk); });
    }
    process.exitCode = await new Promise((resolve, reject) => {
      child.once('error', reject);
      child.once('close', code => resolve(code ?? 1));
    });
  } finally {
    fs.closeSync(log);
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
