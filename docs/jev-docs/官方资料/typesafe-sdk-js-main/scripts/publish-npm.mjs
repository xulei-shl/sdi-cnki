// Publish the already-tested tarball. A retry can skip only an identical registry artifact.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";

const files = readdirSync("release").filter((file) => file.endsWith(".tgz"));
if (files.length !== 1) throw new Error("Expected exactly one release tarball");
// The ./ prefix prevents npm from interpreting this as GitHub owner/repository shorthand.
const tarball = `./release/${files[0]}`;
const { name, version } = JSON.parse(readFileSync("package.json", "utf8"));
const integrity = `sha512-${createHash("sha512").update(readFileSync(tarball)).digest("base64")}`;
const existing = spawnSync("npm", ["view", `${name}@${version}`, "dist.integrity", "--json"], {
  encoding: "utf8",
});
if (existing.status === 0) {
  if (JSON.parse(existing.stdout) !== integrity)
    throw new Error("This version is already on npm with different contents");
  console.log(`${name}@${version} is already published with identical contents.`);
} else {
  let error;
  try {
    error = JSON.parse(existing.stdout);
  } catch {
    /* npm can fail before producing JSON */
  }
  if (error?.error?.code !== "E404") throw new Error(`Registry lookup failed: ${existing.stderr}`);
  const result = spawnSync(
    "npm",
    ["publish", tarball, "--access", "public", "--tag", "latest", "--provenance"],
    {
      stdio: "inherit",
    },
  );
  if (result.status !== 0) process.exit(result.status ?? 1);
}
