// omp-privacy-guard — the ~/.dotfiles repo is PUBLIC (fresh-VM clone without
// auth). Agent layer of the privacy guardrail:
//   .githooks/pre-commit  -> staged content (read from the index)
//   .githooks/commit-msg  -> the commit message
//   .githooks/pre-push    -> every commit a push publishes (content + messages)
//   this extension        -> keeps an agent from switching those hooks off
// The hooks do the scanning, when git runs, on what git actually commits and
// pushes, so `git add x && git commit` is covered. This blocks the ways
// around them for a repo that ships scripts/private-patterns.txt: --no-verify
// (and commit's -n), a core.hooksPath override, and a clone whose hooksPath
// isn't .githooks. The decision is scripts/git-guard.py, shared with
// Claude's PreToolUse hook (config/claude/settings.json): one rule set.
// Project names and board bookkeeping are fine by owner decision
// (2026-10-05) — tune private-patterns.txt with the owner, never bypass.
export default function (api) {
  var fs = require("fs");
  var exec = require("child_process").execFileSync;
  var GUARD = (process.env.HOME || "") + "/.dotfiles/scripts/git-guard.py";

  api.on("tool_call", async function (event) {
    if (event.toolName !== "bash") return;
    var cmd = String((event.input || {}).command || "");
    if (cmd.indexOf("git") < 0 || !fs.existsSync(GUARD)) return;
    var out;
    try {
      out = JSON.parse(String(exec("python3", [GUARD, "--check", cmd, "--cwd", process.cwd()], { stdio: ["ignore", "pipe", "pipe"], timeout: 15000 })));
    } catch (e) {
      return; // the guard itself failed: the git hooks still run
    }
    if (out && out.block) {
      return {
        block: true,
        reason: "Privacy guard: " + out.reason + "\nNever bypass the privacy hooks of this PUBLIC repo.",
      };
    }
  });
}
