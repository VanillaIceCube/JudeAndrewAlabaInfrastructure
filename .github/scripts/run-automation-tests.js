"use strict";

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { workflowIntegrationTests } = require("./validate-workflows");

const testDir = path.resolve(__dirname, "../tests");
const tests = fs.globSync(["unit/*.test.js", "integration/*.test.js"], {
  cwd: testDir,
  exclude: workflowIntegrationTests,
}).sort().map(file => path.join(testDir, file));
if (!tests.length) throw new Error(`No .test.js automation tests found in ${testDir}`);

const result = spawnSync(process.execPath, ["--test", ...tests], { stdio: "inherit" });
if (result.error) throw result.error;
if (result.signal) console.error(`Automation tests stopped by ${result.signal}`);
process.exitCode = result.status ?? 1;
