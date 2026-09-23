// omp-delegation-guard — structural nudge against the "just hack away
// directly" failure mode (observed live on the prescient agent, 2026-09-23:
// the main agent implemented a whole package itself, never spawning a
// subagent, despite the orchestrator role text).
//
// Identity-free by empirical necessity: task workers execute in-process
// (ancestor-walk probe — no separate omp process per worker) and their tool
// executions do NOT fire on the main event bus (verified: zero write events
// while a worker created files). The task tool is ASYNC — its tool_result is
// a spawn ack, not the worker's outcome. So every edit/write execution this
// extension sees belongs to the MAIN agent; that is exactly what we count.
// DIRECT_THRESHOLD consecutive direct production executions → one nextTurn
// nudge per streak. A task spawn resets the streak (delegation happened).
// Tier-agnostic by design: fires the same whether the main agent runs
// premium or workhorse. DELEGATION_GUARD_DEBUG=1 traces decisions on stderr.
const DIRECT_THRESHOLD = 3;
const PRODUCTION_TOOLS = new Set(["write", "edit", "multiedit", "create_file", "apply_patch"]);

export default function (api) {
  let directStreak = 0;
  let nudgedAtStreak = -1;

  api.on("tool_execution_start", (event) => {
    const tool = (event.toolName || "").toLowerCase();
    const dbg = process.env.DELEGATION_GUARD_DEBUG;
    if (tool === "task") {
      directStreak = 0;
      if (dbg) console.error("[delegation-guard] task spawn -> streak reset");
      return;
    }
    if (PRODUCTION_TOOLS.has(tool)) {
      directStreak++;
      if (dbg) console.error(`[delegation-guard] direct ${tool} -> streak=${directStreak}`);
    }
  });

  api.on("turn_end", () => {
    const dbg = process.env.DELEGATION_GUARD_DEBUG;
    if (directStreak >= DIRECT_THRESHOLD && nudgedAtStreak !== directStreak) {
      nudgedAtStreak = directStreak;
      if (dbg) console.error(`[delegation-guard] nudging at streak=${directStreak}`);
      api.sendMessage(
        {
          customType: "delegation-nudge",
          content: [
            {
              type: "text",
              text: `STRUCTURAL DELEGATION GUARD: You have made ${directStreak} consecutive direct write/edit calls. You are the orchestrator — implementation belongs to workers. Delegate the work with a directive spec (target files, changes, acceptance criteria) via the task tool, or state in one line why this is a trivial drive-by fix — but the default is delegation.`,
            },
          ],
        },
        { deliverAs: "nextTurn" }
      );
    }
  });
}
