const fs = require('node:fs');
const path = require('node:path');

function check(text, name) {
  const errors = [];
  text.split(/\r?\n/).forEach((line, i) => {
    const match = line.match(/^\s*(?:-\s*)?uses:\s*["']?([^\s"'#]+)["']?(.*)$/);
    if (match && !match[1].startsWith('./')) {
      const valid = match[1].startsWith('docker://')
        ? /@sha256:[0-9a-f]{64}$/.test(match[1]) : /@[0-9a-f]{40}$/.test(match[1]);
      if (!valid || !/\s+#\s*\S/.test(match[2])) errors.push(`${name}:${i + 1}: external actions require an immutable SHA and readable version comment`);
    }
    if (/^\s*permissions:\s*(?:write-all|read-all)/.test(line)) errors.push(`${name}:${i + 1}: enumerate required permissions`);
    if (/^\s*pull_request_target\s*:/.test(line)) errors.push(`${name}:${i + 1}: privileged PR-target execution requires a separately reviewed policy`);
  });
  return errors;
}

function audit(root) {
  const errors = [];
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(file);
      else if (/\.ya?ml$/.test(file)) errors.push(...check(fs.readFileSync(file, 'utf8'), path.relative(root, file)));
    }
  }
  walk(path.join(root, '.github'));
  return errors;
}
module.exports = { check, audit };
if (require.main === module) {
  const errors = audit(process.cwd());
  if (errors.length) { console.error(errors.join('\n')); process.exitCode = 1; }
  else console.log('Workflow security: immutable external references and explicit grant policy passed.');
}
