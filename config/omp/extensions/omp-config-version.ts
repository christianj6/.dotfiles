// omp-config-version — snapshots the dotfiles config version per agent run.
// config/omp/VERSION (a plain incrementing integer) is bumped as the harness
// config evolves. The version VALUE is captured once per process (an agent
// started at v22 keeps v22 even if the repo moves on mid-session), but the
// config-version entry is injected into the session transcript on EVERY
// before_agent_start: long-running omp processes host MULTIPLE sessions
// over their lifetime (the user's REPL flow starts new sessions in the same
// process), and a once-per-process flag starved later sessions of their
// entry (observed live 2026-09-24: heinzel-exploration's new session had
// zero entries). The herdr omp-watch plugin reads the NEWEST such entry per
// transcript and names the roster entry "omp-v<N>". Entries are ~150 bytes
// and the watcher renames only when the version changes, so per-run
// injection costs nothing visible.
//
// VERSION is read from ~/.omp/agent/VERSION (env PI_CODING_AGENT_DIR
// honored) — a setup.sh symlink to config/omp/VERSION. The agent-dir path
// is used instead of import.meta because omp's extension loader transforms
// import metadata. Fails silently if missing/unreadable: a session without
// a version entry simply shows unversioned in the roster.
export default function (api) {
  var cached = null;

  api.on("before_agent_start", async function () {
    try {
      if (cached === null) {
        var fs = require("fs");
        var dir = process.env.PI_CODING_AGENT_DIR
          || require("os").homedir() + "/.omp/agent";
        var raw = fs.readFileSync(dir + "/VERSION", "utf8").trim();
        var v = parseInt(raw, 10);
        if (!(v > 0)) return;
        cached = v;
      }
      return {
        message: {
          customType: "config-version",
          display: false,
          content: "config v" + cached
        }
      };
    } catch (e) {
      if (cached === null) cached = 0; // unreadable: stop retrying, stay unversioned
      console.error("[config-version] skipped: " + (e && e.message));
    }
  });
}
