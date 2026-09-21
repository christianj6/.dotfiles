// omp-img-overlay — WORKAROUND for nvim's lack of :terminal graphics.
// omp's TUI cannot render inline images in this setup (sessions run inside
// nvim, whose :terminal has no kitty-graphics support), so image blocks in
// tool results are invisible to the user. This extension forwards them to
// the herdr pane-graphics overlay via the herdr-img CLI: the image appears
// bottom-left over the pane and auto-clears after 12s. Remove this file
// (and herdr-img) once nvim :terminal gains graphics rendering/passthrough.

export default function (pi) {
  var cp, fs, HERDR_IMG, lastKey = "", lastAt = 0;
  try {
    cp = require("child_process");
    fs = require("fs");
    var os = require("os");
    HERDR_IMG = os.homedir() + "/.local/bin/herdr-img";
    if (!fs.existsSync(HERDR_IMG)) {
      console.error("[img-overlay] herdr-img not installed — disabled");
      return;
    }
    console.error("[img-overlay] loaded (tool_result -> herdr pane overlay)");
  } catch (e) {
    console.error("[img-overlay] init failed: " + (e && e.message));
    return;
  }

  // Deep-scan for image content blocks; shapes vary by tool:
  //   {type:"image", data:<base64>, mimeType}            — omp native
  //   {type:"image", image:"data:image/...;base64,..."}  — MCP-style
  //   {type:"image", path:<file>}                        — file-backed
  function collectImages(node, out, depth) {
    if (!node || typeof node !== "object" || depth > 6) return;
    if (Array.isArray(node)) {
      for (var i = 0; i < node.length; i++) collectImages(node[i], out, depth + 1);
      return;
    }
    if (node.type === "image") { out.push(node); return; }
    if (typeof node.image === "string" && node.image.indexOf("data:image/") === 0) {
      out.push({ type: "image", data: node.image });
      return;
    }
    for (var k in node) {
      if (typeof node[k] === "object" && node[k] !== null) collectImages(node[k], out, depth + 1);
    }
  }

  pi.on("tool_result", function (event) {
    try {
      var imgs = [];
      collectImages(event && event.content, imgs, 0);
      collectImages(event && event.details, imgs, 0);
      if (!imgs.length) return;
      var img = imgs[0]; // one overlay at a time
      var tmp = "/tmp/omp-img-overlay-" + process.pid + ".png";
      var payload = img.data || img.base64 || "";
      var blob = typeof payload === "string"
        ? payload.match(/^blob:sha256:([0-9a-f]{64})$/) : null;
      if (blob) {
        // omp blob store: content-addressed file + optional typed sidecar
        // (image block data is persisted as the blob ref, not base64)
        var agentDir = process.env.PI_CODING_AGENT_DIR || (os.homedir() + "/.omp/agent");
        var extn = ((img.mimeType || "").split("/")[1] || "").replace(/[^a-z0-9]/gi, "");
        var side = agentDir + "/blobs/" + blob[1] + (extn ? "." + extn : "");
        var canon = agentDir + "/blobs/" + blob[1];
        tmp = fs.existsSync(side) ? side : (fs.existsSync(canon) ? canon : "");
        if (!tmp) {
          console.error("[img-overlay] blob file missing for " + blob[1]);
          return;
        }
      } else if (typeof payload === "string" && payload.indexOf("data:") === 0) {
        fs.writeFileSync(tmp, Buffer.from(payload.slice(payload.indexOf(",") + 1), "base64"));
      } else if (typeof payload === "string" && payload.length > 0) {
        fs.writeFileSync(tmp, Buffer.from(payload, "base64"));
      } else if (typeof img.path === "string" && fs.existsSync(img.path)) {
        tmp = img.path;
      } else {
        return;
      }
      var key = tmp + ":" + (payload || "").length;
      var now = Date.now();
      if (key === lastKey && now - lastAt < 2000) return; // dedupe bursts
      lastKey = key; lastAt = now;
      // herdr-img auto-clears the overlay after --timeout seconds
      cp.execFile(HERDR_IMG, [tmp, "--timeout", "12"], { timeout: 8000 },
        function (err) {
          if (err) console.error("[img-overlay] " + (err.message || err));
        });
    } catch (e) {
      console.error("[img-overlay] " + (e && e.message || e));
    }
  });
}
