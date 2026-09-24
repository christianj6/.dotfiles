// omp-scope-filter — scopes the personal planning layer out of work sessions.
// The Development board (Trello) is personal-only, but APPEND_SYSTEM.md is a
// user-level context file: its board bullets and the issue-tracker-trello
// skill entry are injected into EVERY omp session, including Tallence work
// sessions (observed live 2026-09-23: a thor agent tried to create Trello
// cards). The board-checkpoint hook already stays silent for work scope;
// this extension handles the prompt layer: on before_provider_request (the
// proven extension event carrying the LLM payload), for work-scope sessions
// it scrubs personal-planning references from the system prompt — which lives
// in payload.instructions (Responses-style payload; there is no payload.system)
// — and from any system items in payload.input, in place.
//
// Matching is SUBSTRING-based on distinctive phrases, not line prefixes:
// omp's prompt template renumbers APPEND_SYSTEM bullets (they arrive as
// "4. All significant..." not "- All significant..."), and mnemopi memories
// quoting earlier trial transcripts are injected into instructions too —
// both are caught by the phrase list. Grill / arch-review / wayfinder
// preferences stay — wayfinder falls back to its local-markdown tracker.
// Scope detection resolves herdr/git worktrees to their main repo (see
// omp-board-checkpoint.ts workScope). Fail-open.
// SCOPE_FILTER_DEBUG=1 traces on stderr.
export default function (api) {
  var WORK_MARKER = "Desktop/tallence";
  var STRIP_SUBSTRINGS = [
    "issue-tracker-trello",
    "All significant dev work traces",
    "Development-board card",
    "Development board checkpoint",
    "Session checkpoint:",
    "the board is the roadmap source of truth",
    "the board is the long-term memory",
    "fold the work into an epic",
  ];

  function workScope(cwd) {
    var fs = require("fs");
    var path = require("path");
    var dir = cwd;
    for (var i = 0; i < 20; i++) {
      var gitPath = path.join(dir, ".git");
      if (fs.existsSync(gitPath)) {
        var st = fs.statSync(gitPath);
        if (st.isDirectory()) return dir.indexOf(WORK_MARKER) !== -1;
        var m = /gitdir:\s*(.+)/.exec(fs.readFileSync(gitPath, "utf8"));
        if (m) return m[1].replace(/\/\.git\/worktrees\/.*$/, "").indexOf(WORK_MARKER) !== -1;
        return false;
      }
      var parent = path.dirname(dir);
      if (parent === dir) return false;
      dir = parent;
    }
    return false;
  }

  function lineStripped(line) {
    for (var i = 0; i < STRIP_SUBSTRINGS.length; i++) {
      if (line.indexOf(STRIP_SUBSTRINGS[i]) !== -1) return true;
    }
    return false;
  }

  function scrubText(text) {
    var lines = String(text).split("\n");
    var out = [];
    for (var i = 0; i < lines.length; i++) {
      if (!lineStripped(lines[i])) out.push(lines[i]);
    }
    return out.join("\n");
  }

  function scrubContent(content) {
    if (typeof content === "string") {
      return content.indexOf(STRIP_SUBSTRINGS[0]) !== -1 || content.indexOf(STRIP_SUBSTRINGS[1]) !== -1
        ? { text: scrubText(content), hit: true }
        : { text: content, hit: false };
    }
    if (Array.isArray(content)) {
      var hit = false;
      var blocks = content.map(function (block) {
        if (block && typeof block.text === "string" && lineStripped(block.text)) {
          hit = true;
          return Object.assign({}, block, { text: scrubText(block.text) });
        }
        return block;
      });
      return { text: blocks, hit: hit };
    }
    return { text: content, hit: false };
  }

  api.on("before_provider_request", async function (event) {
    try {
      var payload = event && event.payload;
      if (!payload) return;
      if (!workScope(process.cwd())) return;
      var scrubbed = 0;

      if (typeof payload.instructions === "string" && lineStripped(payload.instructions)) {
        payload.instructions = scrubText(payload.instructions);
        scrubbed++;
      }
      if (Array.isArray(payload.input)) {
        for (var i = 0; i < payload.input.length; i++) {
          var m = payload.input[i];
          if (!m || m.role !== "system") continue;
          var r = scrubContent(m.content);
          if (r.hit) { m.content = r.text; scrubbed++; }
        }
      }
      if (process.env.SCOPE_FILTER_DEBUG) {
        console.error("[scope-filter] work scope; scrubbed=" + scrubbed);
      }
    } catch (e) {
      console.error("[scope-filter] skipped: " + (e && e.message));
    }
  });
}
