// omp-claude-done-watch — the coordinator gets a pulse when its workhorse settles.
// Hooks turn_end (omp-delegation-guard style: turn handlers can't return injects,
// so notes go out via api.sendMessage nextTurn): enumerate herdr agents named
// claude-*, diff agent_status against the last turn, and when one transitions
// working|blocked -> idle|done inject a settle note carrying the pane's tail —
// "⟨claude-heinzel⟩ settled (working -> idle). Tail: ..." — so the orchestrator
// sees the report without polling herdr by hand. The heavier read is delegated:
// the note names the agent; omp spawns the ClaudeWatcher subagent (agents dir)
// on demand to produce the full GREEN/AMBER/RED digest. Communication with
// herdr shells out via the omp-herdr-guard sweep prefix (HERDR_* must not leak
// into child processes). Fail-silent end to end: herdr missing, spawn errors,
// JSON parse failures and pane-tail hiccups never crash the turn.
// CLAUDE_WATCH_DEBUG=1 traces on stderr (BOARD_CHECKPOINT_DEBUG style).

// SETTLED_PRIOR: statuses that mean "was still doing something" the turn before.
var SETTLED_PRIOR = { working: true, blocked: true };
// SETTLED_NOW: statuses that mean "now waiting on me" — the settle moment.
var SETTLED_NOW = { idle: true, done: true };
// MAX_NOTES_PER_TURN: a burst (two panes settling same turn) stays one message.
var MAX_NOTES_PER_TURN = 2;

export default function (api) {
  var cp = null;
  var SEEN = new Map(); // agent name -> prior agent_status (dynamic membership)

  function sh(cmd) {
    // argv: /bin/sh -c "env -u HERDR_... herdr agent <cmd>" — the sweep prefix
    // (identical to omp-herdr-guard's rewrite) strips our HERDR_* env before herdr.
    var r = cp.spawnSync("/bin/sh", ["-c", cmd], { encoding: "utf8", timeout: 4000 });
    if (!r || r.error || r.status !== 0) return null;
    return r.stdout;
  }

  function debug(msg) {
    if (process.env.CLAUDE_WATCH_DEBUG) console.error("[claude-watch] " + msg);
  }

  // sh sweep + herdr agent list — CLI shape: {"id":"cli:agent:list","result":{"agents":[{name, agent_status, ...}]}}
  function claudes() {
    var agents = [];
    try {
      var parsed = JSON.parse(sh("env $(printenv | cut -d= -f1 | grep '^HERDR_' | sed 's/^/-u /' | tr '\\n' ' ') herdr agent list"));
      agents = (parsed && parsed.result && parsed.result.agents) || [];
    } catch (e) {
      debug("agent list failed: " + (e && e.message));
      return null; // herdr missing / spawn error / bad JSON: silent skip this turn
    }
    return agents.filter(function (a) {
      return a && typeof a.name === "string" && a.name.slice(0, 7) === "claude-" && a.agent_status;
    });
  }

  // sh herdr agent read recent-unwrapped — 30 lines of terminal back-scroll
  function paneTail(name) {
    var out = sh("env $(printenv | cut -d= -f1 | grep '^HERDR_' | sed 's/^/-u /' | tr '\\n' ' ') herdr agent read " + name + " --source recent-unwrapped --lines 30");
    if (!out) return "(pane tail unavailable)";
    return out.length > 1500 ? "…" + out.slice(out.length - 1500) : out;
  }

  api.on("turn_end", function () {
    try {
      if (!cp) cp = require("child_process");
    } catch (e) {
      debug("child_process unavailable — disabled");
      return;
    }
    try {
      var agents = claudes();
      if (!agents) {
        debug("herdr agent list unavailable this turn");
        return;
      }
      var settling = [];
      agents.forEach(function (a) {
        var prior = SEEN.get(a.name);
        SEEN.set(a.name, a.agent_status);
        if (SETTLED_PRIOR[prior] && SETTLED_NOW[a.agent_status]) {
          settling.push({ name: a.name, prior: prior, status: a.agent_status });
        }
      });
      debug(settling.length + " settling of " + agents.length);
      settling.slice(0, MAX_NOTES_PER_TURN).forEach(function (a) {
        api.sendMessage(
          {
            customType: "claude-settled",
            content: [
              { type: "text", text: "⟨" + a.name + "⟩ settled (" + a.prior + " -> " + a.status + "). Tail: " + paneTail(a.name) },
            ],
          },
          { deliverAs: "nextTurn" }
        );
      });
    } catch (e) {
      debug("turn_end skipped: " + (e && e.message));
    }
  });
}
