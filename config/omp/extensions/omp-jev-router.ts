// omp-jev-router — TypeSafe Jev context pruning for omp.
// Hooks before_provider_request: finds function_call_output items (tool
// results), batch-evaluates relevance via Jev fan-out (one Noul question
// per chunk), and replaces low-relevance outputs with placeholders.
//
// Env:
//   JEV_API_KEY    TypeSafe API key
//   JEV_THRESHOLD  prune when relevance probability < threshold [0.2]
//   JEV_MODE       "prune" (default) | "observe" | "off"

export default function (api) {
  console.error("[jev-router] extension loaded");
  var JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone";
  var THRESHOLD = parseFloat(process.env.JEV_THRESHOLD || "0.2");
  var MODE = process.env.JEV_MODE || "prune";
  var MAX_CHARS = 6000;
  var evaluated = new Set();
  var pruned = new Set();

  function getApiKey() {
    if (process.env.JEV_API_KEY) return process.env.JEV_API_KEY;
    try {
      var fs = require("fs");
      var envPath = require("os").homedir() + "/.dotfiles/.env";
      var src = fs.readFileSync(envPath, "utf-8");
      for (var line of src.split("\n")) {
        if (line.startsWith("JEV_API_KEY=")) return line.split("=", 2)[1];
      }
    } catch (e) {}
    return null;
  }

  function hashContent(text) {
    var h = 0;
    for (var i = 0; i < text.length; i++) h = ((h << 5) - h + text.charCodeAt(i)) | 0;
    return (h >>> 0).toString(36);
  }

  function extractQuery(input) {
    for (var i = input.length - 1; i >= 0; i--) {
      if (input[i].role === "user") {
        var content = input[i].content;
        if (typeof content === "string") return content;
        if (Array.isArray(content)) {
          return content.filter(function(c) { return c.type === "input_text"; })
            .map(function(c) { return c.text || ""; }).join(" ");
        }
      }
    }
    return "";
  }

  function extractToolOutputs(input) {
    var results = [];
    for (var i = 0; i < input.length; i++) {
      var item = input[i];
      if (item.type !== "function_call_output") continue;
      var output = typeof item.output === "string" ? item.output : "";
      if (output.length < 100 || output.indexOf("[context router") >= 0) continue;
      var h = hashContent(output);
      if (evaluated.has(h) || pruned.has(h)) continue;
      results.push({ index: i, hash: h, output: output });
    }
    return results;
  }

  api.on("before_provider_request", async function (event) {
    if (MODE === "off") return;
    var apiKey = getApiKey();
    if (!apiKey) return;

    var payload = event.payload;
    if (!payload || !payload.input || !Array.isArray(payload.input)) return;

    var query = extractQuery(payload.input);
    if (!query) return;

    for (var di = 0; di < payload.input.length; di++) {
        var item = payload.input[di];
        var otype = typeof item.output;
        var olen = typeof item.output === "string" ? item.output.length : 0;
        console.error("[jev-router:dbg] item[" + di + "] type=" + (item.type || "?") + " role=" + (item.role || "?") + " output_type=" + otype + " output_len=" + olen);
    }
    var unevaluated = extractToolOutputs(payload.input);
    if (unevaluated.length === 0) return;
    unevaluated.forEach(function(c) { evaluated.add(c.hash); });

    try {
      // fan-out: state = query + chunks, one Noul question per chunk
      var state = { user_query: query };
      var questions = {};
      var keyToIndex = {};
      unevaluated.forEach(function(c, idx) {
        var text = c.output.length > MAX_CHARS ? c.output.slice(0, MAX_CHARS) + "..." : c.output;
        state["chunk_" + idx] = text;
        var qKey = "rel_" + idx;
        questions[qKey] = {
          type: "noul",
          instructions: "Is the content in chunk_" + idx + " relevant to solving the user query? Chunks providing code, configuration, command output, diagnostics, or state information needed for the query are relevant. Unrelated content is not."
        };
        keyToIndex[qKey] = idx;
      });

      var body = JSON.stringify({ state: state, model: "jev-latest", questions: questions });
      var resp = await fetch(JEV_ENDPOINT, {
        method: "POST",
        headers: { "Authorization": "Bearer " + apiKey, "Content-Type": "application/json" },
        body: body,
        signal: AbortSignal.timeout(15000)
      });
      if (!resp.ok) throw new Error("Jev API " + resp.status);
      var data = await resp.json();

      var prunedCount = 0;
      for (var qKey in (data.answers || {})) {
        var answer = data.answers[qKey];
        var idx = keyToIndex[qKey];
        if (idx === undefined || answer.noul === undefined) continue;
        var prob = answer.noul;
        if (prob >= THRESHOLD) continue;

        var entry = unevaluated[idx];
        pruned.add(entry.hash);
        prunedCount++;
        payload.input[entry.index].output =
          "[context router: tool output omitted, relevance " + (prob * 100).toFixed(0) + "%, " + entry.output.length + " chars]";
      }
      if (prunedCount > 0) {
        console.error("[jev-router] pruned " + prunedCount + "/" + unevaluated.length + " tool outputs (threshold " + THRESHOLD + ")");
      }
    } catch (err) {
      console.error("[jev-router] error (fail open): " + (err.message || err));
    }
  });
}
