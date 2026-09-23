// omp-board-checkpoint — the Development board announces itself at session start.
// Solves: prompt-level "session checkpoint" bullets get skipped when the user
// hands the agent a direct task (observed live on the prescient agent,
// 2026-09-23). Hooks before_agent_start ONCE per process and injects a short
// custom message ONLY when there is something actionable for this project:
//   - needs-triage cards (the human's admin lane)
//   - In Progress cards (resume or release)
//   - no Roadmap — <project> card (the anti "hack away from memory" trigger)
// Fail-open and silent: board unreachable, work-scope cwd (Tallence), or
// nothing actionable → no message, session starts untouched. Set
// BOARD_CHECKPOINT_DEBUG=1 to trace decisions on stderr.
export default function (api) {
  var BOARD_ID = process.env.DEV_BOARD_ID || "6ab3e379437eaab1279a7e77";
  var CRED_FILES = ["/.omp/agent/.env", "/.dotfiles/.env"];
  var done = false;

  function creds() {
    if (process.env.TRELLO_KEY && process.env.TRELLO_TOKEN) {
      return { key: process.env.TRELLO_KEY, token: process.env.TRELLO_TOKEN };
    }
    try {
      var fs = require("fs");
      var home = require("os").homedir();
      for (var i = 0; i < CRED_FILES.length; i++) {
        var p = home + CRED_FILES[i];
        if (!fs.existsSync(p)) continue;
        var t = fs.readFileSync(p, "utf8");
        var k = /TRELLO_KEY=(\S+)/.exec(t);
        var tok = /TRELLO_TOKEN=(\S+)/.exec(t);
        if (k && tok) return { key: k[1], token: tok[1] };
      }
    } catch (e) {}
    return null;
  }

  function label(card, name) {
    return (card.labels || []).some(function (l) { return l.name === name; });
  }

  api.on("before_agent_start", async function (event) {
    var DBG = process.env.BOARD_CHECKPOINT_DEBUG;
    if (done) return;
    done = true;
    try {
      var cwd = (event && (event.cwd || (event.ctx && event.ctx.cwd))) || process.cwd();
      if (DBG) console.error("[board-checkpoint] fired; cwd=" + cwd);
      if (!cwd || cwd.indexOf("Desktop/tallence") !== -1) {
        if (DBG) console.error("[board-checkpoint] skip: work scope or no cwd");
        return;
      }
      var c = creds();
      if (!c) {
        if (DBG) console.error("[board-checkpoint] skip: no creds");
        return;
      }
      var project = cwd.split("/").filter(Boolean).pop();

      var u = new URL("https://api.trello.com/1/boards/" + BOARD_ID + "/cards");
      u.searchParams.set("key", c.key);
      u.searchParams.set("token", c.token);
      u.searchParams.set("fields", "name,idList,idMembers,labels");
      var res = await fetch(u, { signal: AbortSignal.timeout(4000) });
      if (DBG) console.error("[board-checkpoint] cards status=" + res.status);
      if (!res.ok) return;
      var cards = await res.json();

      var ul = new URL("https://api.trello.com/1/boards/" + BOARD_ID + "/lists");
      ul.searchParams.set("key", c.key);
      ul.searchParams.set("token", c.token);
      ul.searchParams.set("fields", "name");
      var rl = await fetch(ul, { signal: AbortSignal.timeout(4000) });
      if (DBG) console.error("[board-checkpoint] lists status=" + rl.status);
      if (!rl.ok) return;
      var lists = await rl.json();
      var listId = {};
      lists.forEach(function (l) { listId[l.name] = l.id; });

      var names = function (cs) { return cs.slice(0, 3).map(function (card) { return card.name; }).join("; "); };
      var lines = [];

      var triage = cards.filter(function (card) {
        return label(card, "needs-triage") && (label(card, project) || !(card.labels || []).some(function (l) { return l.name; }));
      });
      if (triage.length) lines.push("needs-triage (" + triage.length + "): " + names(triage) + " — triage first");

      var inprog = cards.filter(function (card) { return card.idList === listId["In Progress"] && label(card, project); });
      if (inprog.length) lines.push("In Progress (" + inprog.length + "): " + names(inprog) + " — resume or release");

      var roadmap = cards.some(function (card) {
        return card.idList === listId["Maps"] && label(card, "context") && card.name.toLowerCase().indexOf(project.toLowerCase()) !== -1;
      });
      if (DBG) console.error("[board-checkpoint] project=" + project + " cards=" + cards.length + " triage=" + triage.length + " inprog=" + inprog.length + " roadmap=" + roadmap);
      if (!roadmap) lines.push("No Roadmap — " + project + " card yet: create label + roadmap card before significant work (skill://issue-tracker-trello)");

      if (!lines.length) {
        if (DBG) console.error("[board-checkpoint] nothing actionable -> silent");
        return;
      }
      if (DBG) console.error("[board-checkpoint] injecting " + lines.length + " line(s)");
      return {
        message: {
          customType: "board-checkpoint",
          display: true,
          content: "Development board checkpoint (" + project + "):\n" + lines.map(function (l) { return "- " + l; }).join("\n")
        }
      };
    } catch (e) {
      console.error("[board-checkpoint] skipped: " + (e && e.message));
    }
  });
}
