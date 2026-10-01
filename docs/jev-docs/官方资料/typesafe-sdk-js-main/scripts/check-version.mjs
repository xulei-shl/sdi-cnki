// Fails if package metadata, the lockfile, and the runtime version disagree.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

// Snapshot export validates committed metadata, even if the working tree has edits.
const committed = process.argv[2] === "--committed";
const read = (path) =>
  committed
    ? execFileSync("git", ["show", `HEAD:${path}`], { encoding: "utf8" })
    : readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

const versions = {
  "package.json": JSON.parse(read("package.json")).version,
  "package-lock.json": JSON.parse(read("package-lock.json")).version,
  "package-lock.json root": JSON.parse(read("package-lock.json")).packages[""].version,
  "jsr.json": JSON.parse(read("jsr.json")).version,
  "src/version.ts": read("src/version.ts").match(/VERSION = "([^"]+)"/)?.[1] ?? "(none)",
};

const distinct = new Set(Object.values(versions));
if (distinct.size !== 1) {
  console.error("Version mismatch:");
  for (const [file, version] of Object.entries(versions)) console.error(`  ${file}: ${version}`);
  process.exit(1);
}

if (committed) console.log(versions["package.json"]);
