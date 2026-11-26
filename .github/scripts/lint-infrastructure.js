const { execFileSync } = require('node:child_process');

function trackedFiles(...patterns) {
  return execFileSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', ...patterns],
    { encoding: 'utf8' }).split('\0').filter(Boolean);
}

function check(tool, ...args) {
  execFileSync(tool, args, { stdio: 'inherit' });
}

// Actionlint's permission list predates GitHub's Dependabot alerts permission.
check('actionlint', '-ignore', 'unknown permission scope "vulnerability-alerts"');
const shellFiles = trackedFiles('*.sh');
if (shellFiles.length) check('shellcheck', '--', ...shellFiles);
check('uv', 'run', '--locked', 'python', '-m', 'compileall', '-q', 'gateway', 'deploy');
for (const file of trackedFiles('*.js', '*.cjs')) check(process.execPath, '--check', file);
