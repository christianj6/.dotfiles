// omp-board-checkpoint — the Development board opens every session itself.
// History: v1 injected ONLY on actionable states (needs-triage, In Progress,
// missing roadmap) and stayed silent otherwise — observed live 2026-09-23:
// a fresh session in a fully-onboarded project got nothing, skipped the
// prompt-level checkpoint, and the board was "lost in the shuffle". Lesson:
// a source of truth needs a PRESENCE signal, not just alarms. v2 ALWAYS
// injects a compact summary for personal projects (skips work-scope cwd):
//   Roadmap: <gist>          — standing context, one line
//   Epics: <name> — <goal>   — what workstreams exist (max 4)
//   needs-triage / In Progress lines — only when present
// One board GET by the hook, once per process, ~4 lines of context: the
// model never has to remember the board exists. Fail-open and silent on
// creds/network problems. BOARD_CHECKPOINT_DEBUG=1 traces on stderr.
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

  function cap(s, n) {
    s = String(s || "").trim();
    return s.length > n ? s.slice(0, n - 3) + "..." : s;
  }

  function firstLine(text) {
    var lines = String(text || "").split("\n");
    for (var i = 0; i < lines.length; i++) {
      var l = lines[i].trim();
      if (l) return cap(l.replace(/^#+\s*/, ""), 110);
    }
    return "";
  }

  function goalOf(text) {
    var lines = String(text || "").split("\n");
    for (var i = 0; i < lines.length; i++) {
      if (/^##\s*goal/i.test(lines[i])) {
        for (var j = i + 1; j < lines.length; j++) {
          if (lines[j].trim()) return cap(lines[j].replace(/^#+\s*/, "").replace(/^-\s*/, ""), 90);
        }
      }
    }
    return firstLine(text);
  }

  api.on("before_agent_start", async function (event) {
    var DBG = process.env.BOARD_CHECKPOINT_DEBUG;
    if (done) return;
    done = true;
    try {
      var cwd = (event && (event.cwd || (event.ctx && event.ctx.cwd))) || process.cwd();
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
      u.searchParams.set("fields", "name,idList,idMembers,labels,desc");
      var res = await fetch(u, { signal: AbortSignal.timeout(4000) });
      if (DBG) console.error("[board-checkpoint] cards status=" + res.status);
      if (!res.ok) return;
      var cards = await res.json();

      var ul = new URL("https://api.trello.com/1/boards/" + BOARD_ID + "/lists");
      ul.searchParams.set("key", c.key);
      ul.searchParams.set("token", c.token);
      ul.searchParams.set("fields", "name");
      var rl = await fetch(ul, { signal: AbortSignal.timeout(4000) });
      if (!rl.ok) return;
      var lists = await rl.json();
      var listId = {};
      lists.forEach(function (l) { listId[l.name] = l.id; });

      var lines = [];
      var roadmapCard = cards.filter(function (card) {
        return card.idList === listId["Maps"] && label(card, "context") && card.name.toLowerCase().indexOf(project.toLowerCase()) !== -1;
      })[0];
      if (roadmapCard) {
        var gist = firstLine(roadmapCard.desc) || roadmapCard.name;
        lines.push("Roadmap: " + gist);
      }

      var epics = cards.filter(function (card) {
        return card.idList === listId["Maps"] && label(card, "epic") && label(card, project);
      });
      if (epics.length) {
        var items = epics.slice(0, 4).map(function (card) {
          return card.name.replace(/ — .*/, "") + " — " + goalOf(card.desc);
        });
        if (epics.length > 4) items.push("(" + (epics.length - 4) + " more)");
        lines.push("Epics: " + items.join(" | "));
      }

      var triage = cards.filter(function (card) {
        return label(card, "needs-triage") && (label(card, project) || !(card.labels || []).some(function (l) { return l.name; }));
      });
      if (triage.length) lines.push("needs-triage (" + triage.length + "): " + triage.slice(0, 3).map(function (card) { return card.name; }).join("; ") + " — triage first");

      var inprog = cards.filter(function (card) { return card.idList === listId["In Progress"] && label(card, project); });
      if (inprog.length) lines.push("In Progress (" + inprog.length + "): " + inprog.slice(0, 3).map(function (card) { return card.name; }).join("; ") + " — resume or release");

      if (!roadmapCard && !epics.length) {
        lines.push("This project is not tracked yet: create label + Roadmap — " + project + " card before significant work (skill://issue-tracker-trello)");
      }
      if (DBG) console.error("[board-checkpoint] project=" + project + " roadmap=" + !!roadmapCard + " epics=" + epics.length + " lines=" + lines.length);

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
