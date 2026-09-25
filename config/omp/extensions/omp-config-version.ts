// omp-config-version — publishes the dotfiles config version per omp process.
// config/omp/VERSION (a plain incrementing integer) is bumped as the harness
// config evolves. This extension runs at EXTENSION LOAD — i.e. at process
// start, before any UI, session, or agent run — and writes a marker file
// /tmp/omp-config-versions/<pid> containing the version. The herdr omp-watch
// plugin maps each pane to its live omp pid (ancestor-chain matching) and
// reads the marker to name the roster entry "omp-v<N>-<pane>", so:
//   - the version shows the moment the agent registers, prompted or not
//     (before_agent_start fires per RUN, which starved idle/resumed
//     sessions -- observed live 2026-09-24 on heinzel-exploration);
//   - an agent started at v22 keeps v22 while newer processes get v23
//     (the marker is written once per process, never re-read);
//   - nothing touches the LLM stream or the TUI (appendEntry/custom
//     messages either rendered visibly or never fired).
// Fails silently: no marker -> the roster entry stays unversioned.
export default function (api) {
  try {
    var fs = require("fs");
    var dir = process.env.PI_CODING_AGENT_DIR
      || require("os").homedir() + "/.omp/agent";
    var v = parseInt(fs.readFileSync(dir + "/VERSION", "utf8").trim(), 10);
    if (!(v > 0)) return;
    var root = "/tmp/omp-config-versions";
    try {
      fs.mkdirSync(root, { recursive: true });
    } catch (e) {}
    fs.writeFileSync(root + "/" + process.pid, String(v));
  } catch (e) {
    try {
      require("fs").appendFileSync("/tmp/omp-config-version.log",
        new Date().toISOString() + " [" + process.pid + "] skipped: " + (e && e.message) + "\n");
    } catch (e2) {}
  }
}
