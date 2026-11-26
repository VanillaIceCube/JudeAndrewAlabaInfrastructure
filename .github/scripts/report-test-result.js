const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const reports = {
  ingress: ['ingress.log', 'No gateway or ingress check changes.', 'Gateway regression checks did not run. Check scope and prerequisites.'],
  release: ['release-tests.log', 'No release source or test gate changes.', 'Application launch tests did not run. Check scope and prerequisites.'],
  automation: ['automation.log', 'No GitHub automation or tooling changes.', 'Action regressions did not run. Check the preceding validation and setup steps.'],
};
const name = process.argv[2];
if (!Object.hasOwn(reports, name)) throw new Error('Unknown test report: ' + name);
const [filename, skipReason, missingReason] = reports[name];
const { SCOPE, APPLICABLE, OUTCOME, GITHUB_OUTPUT, RUNNER_TEMP } = process.env;
function report(status, detail) {
  fs.appendFileSync(GITHUB_OUTPUT, name + '_status=' + status + '\n' + name + '=' + detail + '\n');
}
if (name === 'automation' && SCOPE !== 'success') {
  report('failure', 'Unable to determine which checks apply.');
} else if (SCOPE === 'success' && APPLICABLE === 'false') {
  report('not-applicable', skipReason);
} else if (OUTCOME === 'success' || OUTCOME === 'failure') {
  execFileSync(process.execPath, [path.join(__dirname, 'summarize-check-log.js'), path.join(RUNNER_TEMP, filename),
    '--name', name, '--status', OUTCOME, '--summary-lines', '120'], { stdio: 'inherit' });
} else {
  report('failure', missingReason);
}
