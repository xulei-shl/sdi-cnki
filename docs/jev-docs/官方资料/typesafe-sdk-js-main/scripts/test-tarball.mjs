// Install the packed artifact in a clean consumer and exercise both package exports.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const files = readdirSync("release").filter((file) => file.endsWith(".tgz"));
if (files.length !== 1) throw new Error("Expected one package tarball");
const consumer = mkdtempSync(join(tmpdir(), "typesafe-consumer-"));
try {
  writeFileSync(join(consumer, "package.json"), '{"private":true}');
  execFileSync(
    "npm",
    [
      "install",
      "--ignore-scripts",
      "--no-audit",
      "--no-fund",
      "--offline",
      resolve("release", files[0]),
    ],
    { cwd: consumer, stdio: "inherit" },
  );
  for (const type of ["commonjs", "module"]) {
    const load =
      type === "module"
        ? 'import * as sdk from "@typesafe-ai/sdk";'
        : 'const sdk = require("@typesafe-ai/sdk");';
    execFileSync(
      process.execPath,
      [
        "--input-type",
        type,
        "--eval",
        `${load}
      if (typeof sdk.TypeSafeClient !== "function" || typeof sdk.choice !== "function")
        throw new Error("Missing package exports");
      const client = new sdk.TypeSafeClient({ apiKey: "package-smoke-test" });
      if (!client) throw new Error("Client construction failed");
    `,
      ],
      { cwd: consumer, stdio: "inherit" },
    );
  }
} finally {
  rmSync(consumer, { recursive: true, force: true });
}
