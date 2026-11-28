const { execFileSync } = require('node:child_process');
const { existsSync } = require('node:fs');
const { lintWorkflows } = require('./validate-workflows');

function trackedFiles(...patterns) {
  return execFileSync('git', ['ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', ...patterns],
    { encoding: 'utf8' }).split('\0').filter(file => file && existsSync(file));
}

function check(tool, ...args) {
  execFileSync(tool, args, { stdio: 'inherit' });
}

lintWorkflows();
const shellFiles = trackedFiles('*.sh');
if (shellFiles.length) check('shellcheck', '--', ...shellFiles);
check('uv', 'run', '--locked', 'python', '-m', 'compileall', '-q', 'gateway', 'deploy');
for (const file of trackedFiles('*.js', '*.cjs')) check(process.execPath, '--check', file);
