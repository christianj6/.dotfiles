// omp-herdr-guard — enforces the RULES.md rule "never run a nested agent CLI
// inside your own herdr pane without stripping HERDR_* env vars".
// Hooks tool_call for bash:
//   1. Explicit HERDR_* assignments anywhere in the command are blocked —
//      herdr's env must never be passed into a child agent session.
//   2. A command whose head is an agent CLI is rewritten to run under
//      `env -u <every HERDR_*>` so the child cannot inherit them.
// Covers the command head only; agent CLIs mid-pipeline are left alone.
export default function (api) {
  var HEAD = "^\\s*((?:[A-Za-z_][A-Za-z0-9_]*=\\S*\\s+)*)(claude|omp|codex|gemini|cursor-agent|opencode|aider)\\b";
  var AGENT_CLI = new RegExp(HEAD);
  var HERDR_ASSIGN = /\bHERDR_[A-Za-z0-9_]+=/;
  // POSIX-portable sweep: emits `-u NAME` per HERDR_* var visible in the invoking shell.
  var SWEEP = "env $(printenv | cut -d= -f1 | grep '^HERDR_' | sed 's/^/-u /' | tr '\\n' ' ')";

  api.on("tool_call", async function (event) {
    if (event.toolName !== "bash") return;
    var cmd = String((event.input || {}).command || "");
    if (!AGENT_CLI.test(cmd)) return;
    if (HERDR_ASSIGN.test(cmd)) {
      return { block: true, reason: "HERDR_* env must not be passed into a nested agent CLI (it would re-enter herdr). Re-run without the HERDR_* variables." };
    }
    if (cmd.indexOf("-u HERDR") !== -1) return; // already swept
    return { input: Object.assign({}, event.input, { command: cmd.replace(new RegExp(HEAD), "$1" + SWEEP + " $2") }) };
  });
}
