// Anti-dithering guard for omp: tracks consecutive turns without a
// write/edit artifact and injects a structural nudge via sendMessage.
//
// The $2.97 zero-output failure (2026-09-15): sonnet at xhigh thinking
// spent 68 turns reading files, grepping, and reflecting — never wrote
// a single file. Prompt-level anti-dithering rules (APPEND_SYSTEM.md)
// are ignored at xhigh thinking because the model rationalizes its way
// past them. This extension enforces the rule STRUCTURALLY: after
// DITHER_THRESHOLD consecutive turns without a write/edit, it injects
// a nextTurn message that the agent MUST address.

const DITHER_THRESHOLD = 5;
const PRODUCTION_TOOLS = new Set(["write", "edit", "multiedit", "create_file", "apply_patch", "task"]);

export default function (api) {
  let turnsWithoutArtifact = 0;
  let lastNudgeTurn = -1;

  api.on("tool_execution_start", (event) => {
    const tool = (event.toolName || "").toLowerCase();
    if (PRODUCTION_TOOLS.has(tool)) {
      // artifact produced — reset the counter
      turnsWithoutArtifact = 0;
    }
  });

  api.on("turn_end", (event) => {
    turnsWithoutArtifact++;
    if (
      turnsWithoutArtifact >= DITHER_THRESHOLD &&
      turnsWithoutArtifact !== lastNudgeTurn
    ) {
      lastNudgeTurn = turnsWithoutArtifact;
      api.sendMessage(
        {
          customType: "anti-dither-nudge",
          content: [
            {
              type: "text",
              text: `STRUCTURAL ANTI-DITHERING GUARD: You have completed ${turnsWithoutArtifact} consecutive turns without writing or editing any file. Stop researching. Write your current understanding to a file NOW — a plan, a skeleton, a test, anything. Then iterate. Do not continue reading or analyzing.`,
            },
          ],
        },
        { deliverAs: "nextTurn" }
      );
    }
  });
}
