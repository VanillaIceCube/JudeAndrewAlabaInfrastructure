// Check workflow permissions, immutable action revisions and repository automation layout.
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { isDeepStrictEqual } = require("node:util");
const YAML = require("yaml");

const workflows = ".github/workflows";
const oldCodeqlGate = workflows + "/gate-codeql.yml";
const codeqlAlerts = workflows + "/alert-codeql.yml";
const actions = ".github/actions";
const scripts = ".github/scripts";
const tests = ".github/tests";
// The ingress step supplies Docker. Application checks supply the caller's Dockerfiles.
const workflowIntegrationTests = ["integration/gateway.test.js", "integration/uv-bootstrap.test.js"];
const fixtures = tests + "/fixtures";
const workflowFile = /^\.github\/workflows\/[^/]+\.ya?ml$/;
const kebab = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const yamlOptions = { schema: "failsafe", stringKeys: true };
const permissionScopes = new Set([
  "actions", "artifact-metadata", "attestations", "checks", "contents", "deployments",
  "discussions", "id-token", "issues", "models", "packages", "pages", "pull-requests",
  "repository-projects", "security-events", "statuses", "vulnerability-alerts",
]);

function check(source, name) {
  const lineCounter = new YAML.LineCounter();
  const doc = YAML.parseDocument(source, { ...yamlOptions, lineCounter });
  const { contents } = doc;
  if (doc.errors.length) {
    return doc.errors.map((error) => name + ":" + lineCounter.linePos(error.pos[0]).line + ": invalid YAML: " + error.message.split("\n")[0]);
  }
  const errors = [];
  const lines = source.split(/\r?\n/);
  function error(node, message) {
    const line = lineCounter.linePos(node?.range?.[0] ?? 0).line;
    errors.push(name + ":" + line + ": " + message);
  }
  if (workflowFile.test(name.replaceAll("\\", "/")) && !(YAML.isMap(contents) && contents.has("permissions"))) {
    errors.push(name + ":1: declare explicit workflow-level permissions");
  }
  YAML.visit(doc, {
    Alias(_, node) {
      error(node, "YAML aliases require explicit declarations in each policy context");
    },
    Pair(_, { key, value }) {
      switch (key?.value) {
        case "<<":
          error(key, "YAML merge keys require explicit policy review");
          break;
        case "uses": {
          if (!YAML.isScalar(value) || typeof value.value !== "string") {
            error(value ?? key, "uses must be a scalar");
            break;
          }
          const ref = value.value;
          if (ref.startsWith("./")) break;
          const pin = ref.startsWith("docker://") ? /^.+@sha256:[a-f0-9]{64}$/ : /^.+@[a-f0-9]{40}$/;
          const line = lines[lineCounter.linePos(value.range[0]).line - 1];
          if (!pin.test(ref) || !/\s+#\s*\S/.test(line)) {
            error(value, "external actions require an immutable SHA and readable version comment");
          }
          break;
        }
        case "permissions":
          if (!YAML.isMap(value)) {
            error(value ?? key, "enumerate required permissions");
            break;
          }
          for (const { key: scope, value: level } of value.items) {
            if (!permissionScopes.has(scope?.value) || !["read", "write", "none"].includes(level?.value)) {
              error(scope, "unknown permission scope or grant");
            }
          }
          break;
        case "on": {
          let triggers = [value];
          if (YAML.isSeq(value)) triggers = value.items;
          if (YAML.isMap(value)) triggers = value.items.map((pair) => pair.key);
          if (triggers.some((node) => node?.value === "pull_request_target")) {
            error(value, "privileged PR-target execution requires a separately reviewed policy");
          }
          break;
        }
      }
    },
  });
  return errors;
}

function effectiveWrites(source, trustedBase) {
  const workflow = YAML.parse(source, { ...yamlOptions, mapAsMap: true });
  if (!(workflow instanceof Map)) throw new Error("workflow must be a YAML mapping");
  function writes(permissions) {
    if (!(permissions instanceof Map)) throw new Error("workflow permissions must enumerate scopes");
    return new Set([...permissions].filter(([, level]) => level === "write").map(([scope]) => scope));
  }
  // Older reviewed workflows may omit defaults. Only explicitly granted writes carry over.
  const defaults = workflow.has("permissions") ? workflow.get("permissions") : trustedBase && new Map();
  const result = new Map([[null, writes(defaults)]]);
  for (const [job, definition] of workflow.get("jobs") ?? []) {
    if (!(definition instanceof Map)) throw new Error("job must be a YAML mapping");
    result.set(job, writes(definition.has("permissions") ? definition.get("permissions") : defaults));
  }
  return result;
}

// Carry only the old CodeQL upload grant when its workflow is retired.
function codeqlUploadJobs(legacy, proposed, base) {
  const previous = YAML.parse(legacy, yamlOptions);
  const next = YAML.parse(proposed, yamlOptions);
  const grants = effectiveWrites(legacy, true);
  const canUpload = id => grants.get(id)?.has("security-events");

  const { workflow_call, ...events } = previous.on ?? {};
  const nextEvents = { ...next.on };
  const reusable = Object.hasOwn(nextEvents, "workflow_call");
  delete nextEvents.workflow_call;
  // AgentHub's reviewed gate scanned main on push. Only the other repositories already had an alert workflow.
  const hub = Object.hasOwn(events, "push");
  if (!events.schedule || hub !== (base === null)) return [];

  // The existing manual trigger gains one checkbox for a scan-only dispatch.
  if (Object.hasOwn(nextEvents, "workflow_dispatch")) {
    const dispatch = nextEvents.workflow_dispatch;
    if (!isDeepStrictEqual(Object.keys(dispatch?.inputs ?? {}), ["scan_only"]) ||
        dispatch.inputs.scan_only.type !== "boolean" || dispatch.inputs.scan_only.default !== "false") return [];
    nextEvents.workflow_dispatch = events.workflow_dispatch;
  }
  if (!isDeepStrictEqual(nextEvents, events)) return [];

  if (reusable) {
    if (hub || workflow_call === undefined ||
        next.on.workflow_call?.inputs?.scan_only?.default !== "true" ||
        !isDeepStrictEqual(previous.env, next.env) || !isDeepStrictEqual(previous.defaults, next.defaults)) return [];
    // Check names vary by caller. Each job receiving upload access keeps its reviewed implementation.
    return ["analyze-python", "analyze-javascript", "analyze-actions"].filter(id => {
      const job = next.jobs?.[id];
      return job && canUpload(id) && isDeepStrictEqual({ ...previous.jobs[id], name: job.name }, job);
    });
  }

  const scan = next.jobs?.scan;
  if (!scan || !["analyze-actions", "analyze"].some(canUpload)) return [];
  const knownScanner = /^VanillaIceCube\/infrastructure\/\.github\/workflows\/alert-codeql\.yml@[a-f0-9]{40}$/.test(scan.uses);
  const inputs = hub ? { languages_in_tree: "true", scan_only: "true" } : { scan_only: "true" };
  const callerKeys = ["name", "uses", "with", "permissions", "if"];
  return knownScanner && isDeepStrictEqual(scan.with, inputs) &&
    Object.keys(scan).every(key => callerKeys.includes(key)) ? ["scan"] : [];
}

function changedGrants(base, proposed, file, retiredCodeql) {
  const approved = base === null ? new Map() : effectiveWrites(base, true);
  if (retiredCodeql && file === codeqlAlerts) {
    for (const job of codeqlUploadJobs(retiredCodeql, proposed, base)) {
      const writes = approved.get(job) ?? new Set();
      writes.add("security-events");
      approved.set(job, writes);
    }
  }
  const errors = [];
  for (const [job, writes] of effectiveWrites(proposed, false)) {
    const context = job === null ? "workflow" : "jobs." + job;
    for (const scope of [...writes].sort()) {
      if (!approved.get(job)?.has(scope)) errors.push(file + ": " + context + " requests " + scope + ": write outside the trusted base grant");
    }
  }
  return errors;
}

function git(root, ...args) {
  // Reject lossily decoded paths or source, including files read from proposed commits.
  const bytes = execFileSync("git", args, { cwd: root, maxBuffer: 32 * 1024 * 1024, stdio: ["ignore", "pipe", "pipe"] });
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

function workflowBlobs(root, revision) {
  if (typeof revision !== "string" || !/^[a-f0-9]{40}$/.test(revision)) throw new Error("expected an exact GitHub commit SHA");
  const records = git(root, "ls-tree", "--full-tree", "-r", "-z", revision + "^{commit}", "--", workflows + "/");
  const blobs = new Map();
  for (const record of records.split("\0").filter(Boolean)) {
    const tab = record.indexOf("\t");
    const file = record.slice(tab + 1);
    if (!workflowFile.test(file)) continue;
    const [mode, kind, oid] = record.slice(0, tab).split(" ");
    if (kind !== "blob" || !["100644", "100755"].includes(mode)) throw new Error(file + ": expected a regular workflow file");
    blobs.set(file, oid);
  }
  return blobs;
}

function compareCommits(base, head, root = process.cwd()) {
  const before = workflowBlobs(root, base);
  const after = workflowBlobs(root, head);
  function read(oid) {
    if (Number(git(root, "cat-file", "-s", oid)) > 1024 * 1024) throw new Error("workflow exceeds the one MiB inspection limit");
    return git(root, "cat-file", "blob", oid);
  }
  const errors = [];
  const retiredCodeql = !after.has(oldCodeqlGate) && before.get(oldCodeqlGate);
  for (const [file, oid] of after) {
    if (before.get(file) === oid) continue;
    const proposed = read(oid);
    const problems = check(proposed, file);
    if (problems.length) {
      errors.push(...problems);
      continue;
    }
    const baseSource = before.has(file) ? read(before.get(file)) : null;
    const transfer = retiredCodeql && file === codeqlAlerts;
    errors.push(...changedGrants(baseSource, proposed, file, transfer ? read(retiredCodeql) : null));
  }
  return errors;
}

function* usesIn(value, seen = new Set()) {
  if (!value || typeof value !== "object" || seen.has(value)) return;
  seen.add(value);
  for (const [key, child] of Object.entries(value)) {
    if (key === "uses" && typeof child === "string") yield child;
    yield* usesIn(child, seen);
  }
}

function repositoryFiles(root) {
  const listing = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", ".github", ":(exclude).github/node_modules/**");
  return new Set(listing.split("\0").filter((name) => name && fs.lstatSync(path.join(root, name), { throwIfNoEntry: false })));
}

function isPolicyYaml(name) {
  // Older consumer revisions kept test data directly under .github/fixtures.
  return /\.ya?ml$/i.test(name) && !name.startsWith(tests + "/") && !name.startsWith(".github/fixtures/");
}

function checkCodeqlPins(root = process.cwd()) {
  const entries = new Set();
  const revisions = new Set();
  let count = 0;
  for (const name of repositoryFiles(root)) {
    if (!isPolicyYaml(name)) continue;
    const document = YAML.parse(fs.readFileSync(path.join(root, name), "utf8"), yamlOptions);
    for (const reference of usesIn(document)) {
      const prefix = "github/codeql-action/";
      if (!reference.toLowerCase().startsWith(prefix)) continue;
      const target = reference.slice(prefix.length);
      const at = target.indexOf("@");
      const entry = at === -1 ? target : target.slice(0, at);
      const revision = at === -1 ? "" : target.slice(at + 1);
      if (!/^[a-f0-9]{40}$/.test(revision)) throw new Error(name + ": CodeQL " + entry + " requires an immutable SHA");
      entries.add(entry);
      revisions.add(revision);
      count++;
    }
  }
  for (const entry of ["init", "analyze"]) {
    if (!entries.has(entry)) throw new Error("Missing CodeQL " + entry + " reference");
  }
  if (revisions.size !== 1) throw new Error("CodeQL action revisions differ; update all entry points atomically");
  return count;
}

function layoutProblem(file, testOwners, testDirectories) {
  const parts = file.split("/");
  const group = parts.slice(0, 2).join("/");
  const name = parts.at(-1);
  const parent = path.posix.dirname(file);
  const fixture = file.startsWith(fixtures + "/") || group === ".github/fixtures";
  if (name === "README.md" && parent === group) return;
  if ([workflows, actions, scripts].includes(group) && (name.includes(".test.") || name.startsWith("test_") || parts.includes("fixtures"))) {
    return "keep automation tests in .github/tests and fixtures in .github/tests/fixtures";
  }
  if (group === workflows && !(parent === workflows && name.endsWith(".yml") && kebab.test(name.slice(0, -4)))) {
    return "put kebab-case .yml workflows directly in .github/workflows";
  }
  const js = name.endsWith(".js") && kebab.test(name.slice(0, -3));
  if (group === scripts && !(parent === scripts && js)) return "put kebab-case .js automation programs directly in .github/scripts";
  if (group === actions && !(parts.length === 4 && (name === "action.yml" || js))) {
    return "keep action.yml and its implementation together in the action directory";
  }
  if (group === tests && !fixture) {
    if (workflowIntegrationTests.includes(file.slice(tests.length + 1))) return;
    if (!testDirectories.includes(parent)) return "put automation suites directly in " + testDirectories.join(" or ");
    if (!name.endsWith(".test.js") || !kebab.test(name.slice(0, -8))) return "use <implementation-name>.test.js";
    if (!testOwners.has(name.slice(0, -8))) return "name the test after its script, action implementation or workflow";
  }
  if (fixture && !kebab.test(path.posix.parse(name).name)) {
    return "use a lowercase, hyphen-separated fixture name";
  }
  if (fixture && /\.(?:[cm]?js|ts|py|sh|ps1|cmd|bat|exe)$/i.test(name)) {
    return "keep supporting data in .github/tests/fixtures and executable tests in .github/tests";
  }
  if (/\.(?:py|sh)$/i.test(name)) return "put standalone GitHub automation in a JavaScript implementation file";
}

function callsActionEntry(step, directory, entry) {
  if (typeof step?.run === "string") {
    // A composite shell step runs the adjacent file using the runner's action directory.
    for (const [, file] of step.run.matchAll(/^\s*(?:exec\s+)?node\s+["']?\$(?:GITHUB_ACTION_PATH|\{GITHUB_ACTION_PATH\})\/([a-z0-9-]+\.js)(?=["'\s]|$)/gm)) {
      if (file === entry) return true;
    }
  }
  if (!step?.uses?.startsWith("actions/github-script@") || typeof step.with?.script !== "string") return false;
  // github-script loads the action module from the checked-out workspace.
  const requireFromWorkspace = /\brequire\(\s*(?:process\.env\.GITHUB_WORKSPACE\s*\+\s*["']|\x60\$\{process\.env\.GITHUB_WORKSPACE\})\/(\.github\/actions\/[a-z0-9-]+\/[a-z0-9-]+\.js)["'\x60]\s*,?\s*\)/g;
  const script = step.with.script.split("\n").filter((line) => !line.trimStart().startsWith("//")).join("\n");
  if (step.env?.ACTION_DIRECTORY === "${{ github.action_path }}") {
    const localModule = /\brequire\(\s*process\.env\.ACTION_DIRECTORY\s*\+\s*["']\/([a-z0-9-]+\.js)["']\s*\)/g;
    if ([...script.matchAll(localModule)].some(([, file]) => file === entry)) return true;
  }
  return [...script.matchAll(requireFromWorkspace)].some(([, file]) => file === directory + "/" + entry);
}

function manifestProblems(document, name, source, files) {
  const { runs } = document;
  if (runs?.using !== "composite" || !Array.isArray(runs.steps)) return [name + ": expected a composite action with runs.steps"];
  const problems = [];
  const directory = path.posix.dirname(name);
  const entry = path.posix.basename(directory) + ".js";
  if (!files.has(directory + "/" + entry)) problems.push(name + ": missing primary action implementation " + entry);
  else if (!runs.steps.some((step) => callsActionEntry(step, directory, entry))) problems.push(name + ": a composite step must invoke " + entry);
  for (const step of runs.steps) {
    if (!step || typeof step !== "object" || Array.isArray(step) || (Object.hasOwn(step, "run") && !step.shell)) {
      problems.push(name + ": a composite run step needs its shell");
    }
  }
  for (const [, script] of source.matchAll(/\$\{?GITHUB_ACTION_PATH\}?\/([a-z0-9.-]+)/g)) {
    if (!files.has(path.posix.join(path.posix.dirname(name), script))) problems.push(name + ": missing action implementation " + script);
  }
  return problems;
}

// A job can load shared tools from an explicitly pinned second checkout.
function missingWorkflowScripts(document, files) {
  const missing = new Set();
  const script = /(?:([\w.-]+)\/)?(\.github\/(?:workflows\/)?scripts\/[a-z0-9-]+\.(?:m?js|cjs|py|sh))\b/g;
  for (const job of Object.values(document.jobs ?? { action: document.runs })) {
    const checkouts = new Set();
    for (const step of job?.steps ?? []) {
      for (const [, directory, file] of JSON.stringify(step).matchAll(script)) {
        if (!files.has(file) && !checkouts.has(directory)) missing.add(file);
      }
      const inputs = step.with ?? {};
      if (/^actions\/checkout@[a-f0-9]{40}$/.test(step.uses) &&
          /^[\w.-]+\/[\w.-]+$/.test(inputs.repository) && /^[a-f0-9]{40}$/.test(inputs.ref) &&
          /^[a-z0-9][a-z0-9-]*$/.test(inputs.path ?? "")) {
        checkouts.add(inputs.path);
      }
    }
  }
  return missing;
}

function audit(root = process.cwd()) {
  const files = repositoryFiles(root);
  const grouped = [tests + "/unit", tests + "/integration"];
  // Older published consumers still discover their suites directly in .github/tests.
  const testDirectories = grouped.some(dir => fs.existsSync(path.join(root, dir))) ? grouped : [tests];
  const testOwners = new Set();
  for (const file of files) {
    if (/^\.github\/(?:scripts\/[^/]+\.js|actions\/[^/]+\/[^/]+\.js|workflows\/[^/]+\.yml)$/.test(file)) {
      testOwners.add(path.posix.parse(file).name);
    }
  }
  const callers = new Map();
  const declaredActions = new Set();
  const errors = [];
  for (const name of [...files].sort()) {
    const parts = name.split("/");
    const group = parts.slice(0, 2).join("/");
    if (group === actions && parts.length >= 4) declaredActions.add(parts.slice(0, 3).join("/"));
    const fullPath = path.join(root, name);
    if ([workflows, actions, scripts].includes(group) && !fs.lstatSync(fullPath).isFile()) {
      errors.push(name + ": workflows and their executable helpers must be regular files");
      continue;
    }
    const layout = layoutProblem(name, testOwners, testDirectories);
    if (layout) errors.push(name + ": " + layout);
    if (!isPolicyYaml(name)) continue;
    const source = fs.readFileSync(fullPath, "utf8");
    const problems = check(source, name);
    if (problems.length) {
      errors.push(...problems);
      continue;
    }
    const document = YAML.parse(source, yamlOptions);
    if (!document || Array.isArray(document) || typeof document !== "object") {
      errors.push(name + ": expected a YAML mapping");
      continue;
    }
    if (![workflows, actions].includes(group)) continue;
    if (parts.at(-1) === "action.yml") errors.push(...manifestProblems(document, name, source, files));
    const targets = new Set();
    callers.set(name, targets);
    for (const reference of usesIn(document)) {
      if (!reference.startsWith("./")) continue;
      let target = reference.slice(2);
      if (path.posix.dirname(target) === actions) target += "/action.yml";
      else if (path.posix.dirname(target) !== workflows || !target.endsWith(".yml")) {
        errors.push(name + ": local uses must name a reusable action or a workflow");
        continue;
      }
      targets.add(target);
      if (!files.has(target)) errors.push(name + ": local uses target " + reference + " is missing");
    }
    // Pinned application deployment workflows are verified against the Infrastructure release template.
    const generatedDeploy = name === workflows + "/ci-deploy.yml" && fs.existsSync(path.join(root, "deploy/production/app.json"));
    if (!generatedDeploy && /^\s*(?:python3?|node)(?:[ \t]+-[A-Za-z]+)*[ \t]+(?:-[ \t]*)?<</m.test(source)) {
      errors.push(name + ": put an embedded Python or JavaScript program in an implementation file");
    }
    for (const script of missingWorkflowScripts(document, files)) {
      errors.push(name + ": missing workflow script " + script);
    }
  }
  const pending = [...callers.keys()].filter((file) => path.posix.dirname(file) === workflows);
  const reachable = new Set(pending);
  while (pending.length) {
    for (const child of callers.get(pending.pop()) ?? []) {
      if (reachable.has(child)) continue;
      reachable.add(child);
      pending.push(child);
    }
  }
  for (const folder of [...declaredActions].sort()) {
    const manifest = folder + "/action.yml";
    if (!kebab.test(path.posix.basename(folder)) || !files.has(manifest)) {
      errors.push(folder + ": each reusable action needs a kebab-case directory and action.yml");
    } else if (!reachable.has(manifest)) {
      errors.push(folder + ": no local workflow or action calls this action");
    }
  }
  return errors;
}

function lintWorkflows() {
  // Actionlint 1.7.12 predates these GitHub.com job fields and the Dependabot alert permission.
  execFileSync("actionlint", [
    "-ignore", '^unknown permission scope "vulnerability-alerts"',
    "-ignore", '^property "workflow_(repository|sha)" is not defined in object type \\{check_run_id: number; container:',
  ], { stdio: "inherit" });
}

function main(args) {
  const [command, base, head] = args;
  let problems;
  if (command === "--lint" && args.length === 1) return lintWorkflows();
  if (command === "--check-codeql-pins" && args.length === 1) {
    console.log("Verified " + checkCodeqlPins() + " aligned immutable CodeQL references.");
    return;
  } else if (command === "--compare-workflow-grants" && args.length === 3) {
    problems = compareCommits(base, head);
  } else if (command === "--audit" && args.length === 1) {
    problems = audit();
    if (process.env.GITHUB_EVENT_NAME === "pull_request") {
      const { pull_request: pr } = JSON.parse(fs.readFileSync(process.env.GITHUB_EVENT_PATH, "utf8"));
      problems.push(...compareCommits(pr.base.sha, pr.head.sha));
    }
  } else {
    throw new Error("Expected --lint, --audit, --check-codeql-pins or --compare-workflow-grants BASE HEAD");
  }
  if (problems.length) throw new Error(problems.join("\n"));
}

module.exports = { audit, changedGrants, check, checkCodeqlPins, lintWorkflows, workflowIntegrationTests };
if (require.main === module) {
  try {
    main(process.argv.slice(2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
