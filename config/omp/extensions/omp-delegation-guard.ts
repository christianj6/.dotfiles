// omp-delegation-guard — structural nudges for orchestrator discipline.
// Fires two nudges, both tier-agnostic:
//   1. DELEGATION NUDGE: DIRECT_THRESHOLD consecutive direct write/edit
//      executions by the main agent → delegate via the task tool.
//   2. SEAM REMINDER: a fan-out turn (2+ workers spawned via one or more
//      task calls) → make the seam contract explicit before workers land,
//      run the integration gate after. Neither worker can see the seam.
//
// Runtime facts (probed 2026-09-23): task workers run as subprocesses that
// load extensions FRESH (per-instance counters), their tool events surface
// on the inherited stderr bus, and workers emit `yield` — a tool main
// sessions never have. So: a process that has seen a `yield` event IS a
// worker → disarmed. Batch fan-outs are ONE task execution whose args.tasks
// carries N items — count workers from args, not executions.
// DELEGATION_GUARD_DEBUG=1 traces decisions on stderr.
const DIRECT_THRESHOLD = 3;
const PRODUCTION_TOOLS = new Set(["write", "edit", "multiedit", "create_file", "apply_patch"]);

export default function (api) {
  let directStreak = 0;
  let nudgedAtStreak = -1;
  let taskSpawnsThisTurn = 0;
  let seenYield = false;
  let seq = 0;

  api.on("tool_execution_start", (event) => {
    const tool = (event.toolName || "").toLowerCase();
    const dbg = process.env.DELEGATION_GUARD_DEBUG;
    if (dbg) console.error(`[delegation-guard] exec seq=${++seq} tool=${tool}`);
    if (tool === "yield") {
      if (!seenYield && dbg) console.error("[delegation-guard] yield seen -> this is a worker process, disarmed");
      seenYield = true;
      return;
    }
    if (tool === "task") {
      const batch = (event.args && event.args.tasks) || [];
      taskSpawnsThisTurn += Math.max(1, batch.length);
      directStreak = 0;
      if (dbg) console.error(`[delegation-guard] task spawn (${batch.length} worker(s)) -> streak reset, turn spawns=${taskSpawnsThisTurn}`);
      return;
    }
    if (PRODUCTION_TOOLS.has(tool)) {
      directStreak++;
      if (dbg) console.error(`[delegation-guard] direct ${tool} -> streak=${directStreak}`);
    }
  });

  api.on("turn_end", () => {
    const dbg = process.env.DELEGATION_GUARD_DEBUG;
    if (seenYield) return; // worker process: never nudge
    if (taskSpawnsThisTurn >= 2) {
      if (dbg) console.error(`[delegation-guard] fan-out detected (${taskSpawnsThisTurn} workers) -> seam reminder`);
      api.sendMessage(
        {
          customType: "seam-contract-reminder",
          content: [
            {
              type: "text",
              text: `STRUCTURAL SEAM GUARD: You are fanning out ${taskSpawnsThisTurn} subagents on one feature. Neither worker can see the seam — only you can. Before their work lands: write the shared contract (interfaces/exports, naming conventions, file-ownership boundaries — no overlap) to a file both specs reference. After both land: run the integration gate (compile/typecheck/build on the combined tree plus the seam flow) before reporting done.`,
            },
          ],
        },
        { deliverAs: "nextTurn" }
      );
    }
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
    taskSpawnsThisTurn = 0;
  });
}
