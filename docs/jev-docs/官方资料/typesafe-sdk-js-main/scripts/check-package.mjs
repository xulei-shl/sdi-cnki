// Runs publint and arethetypeswrong against a fresh `npm pack`.
//
// Done from a script rather than inline so we can drop npm's dry-run flag: when this runs inside
// `npm publish --dry-run` (via prepublishOnly), npm exports npm_config_dry_run=true, the nested
// `npm pack` inside attw then produces no tarball, and attw fails with a confusing ENOENT.
import { spawnSync } from "node:child_process";

const env = { ...process.env };
delete env.npm_config_dry_run;

for (const [cmd, args] of [
  ["publint", []],
  ["attw", ["--pack", "."]],
]) {
  const result = spawnSync(cmd, args, {
    stdio: "inherit",
    env,
    shell: process.platform === "win32",
  });
  if (result.status !== 0) process.exit(result.status ?? 1);
}
