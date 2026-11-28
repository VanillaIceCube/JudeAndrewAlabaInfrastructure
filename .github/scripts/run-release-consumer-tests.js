"use strict";

const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const source = path.resolve(__dirname, "../..");
const consumer = fs.mkdtempSync(path.join(os.tmpdir(), "release-consumer-"));
const production = path.join(consumer, "deploy/production");
const python = process.platform === "win32" ? "python" : "python3";
try {
  fs.mkdirSync(production, { recursive: true });
  for (const file of ["app.json", "compose.yml"]) {
    fs.copyFileSync(path.join(source, "deploy/tests/fixtures", file), path.join(production, file));
  }
  const builder = path.join(production, "build_bundle.py");
  fs.copyFileSync(path.join(source, "deploy/build_bundle.py"), builder);
  const options = { cwd: consumer, stdio: "inherit" };
  execFileSync(python, [builder, "--check-parity", "--source-root", source, "--sync"], options);
  execFileSync(python, [builder, "--check-parity", "--source-root", source], options);
  execFileSync(python, ["-m", "unittest", "discover", "-s", "deploy/tests", "-v"], options);
} finally {
  fs.rmSync(consumer, { recursive: true, force: true });
}
