// omp-compaction-brief — every LLM-written compaction is a handoff brief.
// The owner's five-item brief (config/agents/compaction-brief.md, the one
// source) goes into the summarizer's prompt through omp's `session.compacting`
// hook: its `context` lines are appended to the compaction prompt
// (@oh-my-pi/pi-agent-core compaction.ts, formatAdditionalContext). That hook
// fires on every path that asks an LLM for a summary: /compact, the
// context-full and handoff strategies, and snapcompact's LLM fallback. The
// default snapcompact strategy writes no summary (it archives history as
// images), so it has nothing to shape. Fail-open: no file, no extra context.
export default function (api) {
  var BRIEF = "/.dotfiles/config/agents/compaction-brief.md";

  function brief() {
    try {
      var fs = require("fs");
      var p = require("os").homedir() + BRIEF;
      return fs.existsSync(p) ? fs.readFileSync(p, "utf8").trim() : "";
    } catch (e) {
      return "";
    }
  }

  api.on("session.compacting", function () {
    var text = brief();
    return text ? { context: [text] } : undefined;
  });
}
