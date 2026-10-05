// omp-privacy-guard — the ~/.dotfiles repo is PUBLIC (fresh-VM clone without
// auth). Tool-call layer of the privacy guardrail:
//   .githooks/pre-commit  -> local commits (bypassable with --no-verify)
//   this extension        -> git commit/push bash calls (cannot be bypassed)
//   CI (check-private.yml) -> full tracked-tree audit on push + daily
// A bash call touching git commit|push runs scripts/check-private.py
// --staged against the session repo and blocks on findings. Only repos that
// ship the scanner (scripts/private-patterns.txt present) are affected.
// Board bookkeeping and project names are fine by owner decision
// (2026-10-05) — tune private-patterns.txt with the owner, never bypass.
export default function (api) {
  var GIT_WRITE = /\bgit\b[^|;&]*\b(commit|push)\b/;
  var exec = require("child_process").execSync;

  api.on("tool_call", async function (event) {
    if (event.toolName !== "bash") return;
    var cmd = String((event.input || {}).command || "");
    if (!GIT_WRITE.test(cmd)) return;
    var root = "";
    try {
      root = String(exec("git rev-parse --show-toplevel", { cwd: process.cwd(), stdio: ["ignore", "pipe", "ignore"] })).trim();
    } catch (e) {
      return; // not inside a git repo
    }
    var fs = require("fs");
    if (!fs.existsSync(root + "/scripts/private-patterns.txt")) return; // guard ships only with this repo
    var out = "";
    try {
      exec("python3 scripts/check-private.py --staged", { cwd: root, stdio: ["ignore", "pipe", "pipe"] });
    } catch (e) {
      out = String((e && e.stderr) || e);
      return {
        block: true,
        reason:
          "Privacy guard: staged content matches scripts/private-patterns.txt — private content must not land in this PUBLIC repo.\n" +
          out +
          "\nRemove the content or tune private-patterns.txt with the owner. Never bypass (--no-verify included).",
      };
    }
  });
}
