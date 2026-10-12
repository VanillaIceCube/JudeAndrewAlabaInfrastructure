"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { alertPriority } = require("./sync-security-alerts");

test("critical and high alerts receive incident priority while medium/low vulnerabilities remain backlog work", () => {
  assert.equal(alertPriority("vulnerability", [{ severity: "medium" }, { severity: "critical" }]), "P0");
  assert.equal(alertPriority("vulnerability", [{ severity: "high" }]), "P1");
  assert.equal(alertPriority("vulnerability", [{ severity: "unknown" }]), "P1");
  assert.equal(alertPriority("vulnerability", [{ severity: "low" }, { severity: "medium" }]), "P2");
  assert.equal(alertPriority("malware", [{ severity: "low" }]), "P1");
});

async function collect(feed, alerts, advisoryLookup = async () => ({ data: { type: "reviewed" } })) {
  const action = fs.readFileSync(path.join(__dirname, "action.yml"), "utf8").replaceAll("\r\n", "\n");
  const script = action.split("- name: Fetch open structured alerts")[1]
    .split("        script: |\n")[1].split("\n    - name:")[0]
    .split("\n").map(line => line.replace(/^          /, "")).join("\n");
  let result;
  const github = {
    rest: { codeScanning: { listAlertsForRepo: "codeql" }, dependabot: { listAlertsForRepo: "dependabot" } },
    paginate: async () => alerts,
    request: advisoryLookup,
  };
  const run = Object.getPrototypeOf(async function () {}).constructor;
  await new run("require", "github", "context", "core", "process", script)(
    () => ({ writeFileSync: (_filename, content) => { result = JSON.parse(content); } }),
    github, { repo: { owner: "owner", repo: "infrastructure" } },
    { setOutput() {}, info() {}, setFailed(message) { throw new Error(message); } },
    { env: { FEED: feed, RUNNER_TEMP: "/fixture" } },
  );
  return result;
}

function alert(number, severity, ghsa = `GHSA-${number}`) {
  return { number, html_url: `https://github.com/owner/infrastructure/security/dependabot/${number}`,
    security_advisory: { ghsa_id: ghsa, severity, summary: "Authoritative advisory" },
    dependency: { package: { name: "example", ecosystem: "actions" }, manifest_path: ".github/workflows/ci.yml" },
  };
}

test("vulnerability feed retains every severity and authoritative source link", async () => {
  const source = ["critical", "high", "medium", "low", "unknown"].map((severity, index) => alert(index + 1, severity));
  const result = await collect("vulnerability", source);
  assert.deepEqual(result.alerts.map(value => value.severity), source.map(value => value.security_advisory.severity));
  assert.equal(result.alerts[0].url, source[0].html_url);
});

test("malware classification queries only unique advisories already affecting this repository", async () => {
  const lookedUp = [];
  const result = await collect("malware", [alert(1, "critical", "bad"), alert(2, "high", "bad"), alert(3, "medium", "ordinary")],
    async (_route, params) => {
      lookedUp.push(params.ghsa_id);
      return { data: { type: params.ghsa_id === "bad" ? "malware" : "reviewed" } };
    });
  assert.deepEqual(lookedUp, ["bad", "ordinary"]);
  assert.deepEqual(result.alerts.map(value => value.ref), ["dependabot:1", "dependabot:2"]);
});

test("empty malware feed does not query the global advisory corpus", async () => {
  const result = await collect("malware", [], async () => { throw new Error("Unexpected advisory lookup"); });
  assert.deepEqual(result.alerts, []);
});

test("scanner errors propagate before any group can be synchronized", async () => {
  await assert.rejects(collect("malware", [alert(1, "high")], async () => { throw new Error("API unavailable"); }), /API unavailable/);
});
