// omp-config-version — snapshots the dotfiles config version at agent start.
// config/omp/VERSION (a plain incrementing integer) is bumped as the harness
// config evolves. Because long-running sessions keep their start-time config,
// each agent's version is captured ONCE per process — on the first
// before_agent_start — and injected into the session transcript as a
// config-version custom entry. The herdr omp-watch plugin reads that entry
// per transcript and names the roster entry "omp-v<N>", so older agents keep
// showing their older version while new sessions get the new one.
//
// VERSION is read from ~/.omp/agent/VERSION (env PI_CODING_AGENT_DIR honored)
// — a setup.sh symlink to config/omp/VERSION. The agent-dir path is used
// instead of import.meta because omp's extension loader transforms import
// metadata. Fails silently if missing/unreadable: a session without a
// version entry simply shows unversioned in the roster.
export default function (api) {
  var done = false;

  api.on("before_agent_start", async function () {
    if (done) return;
    done = true;
    try {
      var fs = require("fs");
      var dir = process.env.PI_CODING_AGENT_DIR
        || require("os").homedir() + "/.omp/agent";
      var raw = fs.readFileSync(dir + "/VERSION", "utf8").trim();
      var v = parseInt(raw, 10);
      if (!(v > 0)) return;
      return {
        message: {
          customType: "config-version",
          display: false,
          content: "config v" + v
        }
      };
    } catch (e) {
      console.error("[config-version] skipped: " + (e && e.message));
    }
  });
}
