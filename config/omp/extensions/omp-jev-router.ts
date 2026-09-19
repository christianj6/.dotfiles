// omp-jev-router — TypeSafe Jev per-turn routing + context pruning for omp.
// Hooks before_provider_request and fans ONE Jev call out per request:
//   1. Context pruning: finds function_call_output items (tool results),
//      batch-evaluates relevance (one Noul question per chunk), and
//      replaces low-relevance outputs with placeholders.
//   2. Model routing: classifies the turn (last user message + conversation
//      summary); reasoning probability < 0.4 reroutes to the glm-5.3-flash
//      workhorse, otherwise the premium expert model stays.
//   3. Thinking escalation: difficulty probability > 0.7 raises the
//      payload's reasoning/thinking parameter when present, else logs a
//      recommendation to stderr.
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

  var ROUTE_THRESHOLD = 0.4;
  var THINK_THRESHOLD = 0.7;
  var WORKHORSE_MODEL = "openrouter/z-ai/glm-5.3-flash";
  var MAX_SUMMARY_CHARS = 4000;

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

  function buildSummary(input) {
    var parts = [];
    for (var i = 0; i < input.length; i++) {
      var item = input[i];
      if (item.type === "function_call_output" || !item.role) continue;
      var text = typeof item.content === "string" ? item.content : "";
      if (Array.isArray(item.content)) {
        text = item.content.filter(function(c) { return c.type === "input_text" || c.type === "output_text" || c.type === "text"; })
          .map(function(c) { return c.text || ""; }).join(" ");
      }
      if (!text) continue;
      parts.push(item.role + ": " + text);
    }
    var summary = parts.slice(-12).join(" | ");
    if (summary.length > MAX_SUMMARY_CHARS) summary = "..." + summary.slice(-MAX_SUMMARY_CHARS);
    return summary;
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
    console.error("[jev-router:dbg2] unevaluated=" + unevaluated.length);
    if (unevaluated.length > 0) unevaluated.forEach(function(c) { evaluated.add(c.hash); });

    try {
      // fan-out: state = query + summary + chunks; questions = one Noul
      // relevance question per chunk + turn routing + thinking escalation
      var state = { user_query: query, conversation_summary: buildSummary(payload.input) };
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

      questions.route_turn = {
        type: "noul",
        instructions: "Does responding to this user message require deep analytical reasoning about code architecture, complex debugging, or nuanced design decisions?"
      };
      questions.escalate_thinking = {
        type: "noul",
        instructions: "Does this turn involve a genuinely difficult problem that would benefit from extended thinking?"
      };
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
      var answers = data.answers || {};
      for (var qKey in answers) {
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

      // per-turn model routing
      if (answers.route_turn && answers.route_turn.noul !== undefined) {
        var routeProb = answers.route_turn.noul;
        if (routeProb < ROUTE_THRESHOLD) {
          var prevModel = payload.model;
          payload.model = WORKHORSE_MODEL;
          console.error("[jev-router] route: reasoning prob " + routeProb.toFixed(2) + " < " + ROUTE_THRESHOLD + " -> " + WORKHORSE_MODEL + " (was " + prevModel + ")");
        } else {
          console.error("[jev-router] route: reasoning prob " + routeProb.toFixed(2) + " >= " + ROUTE_THRESHOLD + " -> keep " + payload.model);
        }
      }

      // thinking escalation
      if (answers.escalate_thinking && answers.escalate_thinking.noul !== undefined) {
        var thinkProb = answers.escalate_thinking.noul;
        if (thinkProb > THINK_THRESHOLD) {
          var escalated = false;
          if (payload.reasoning && typeof payload.reasoning === "object") {
            if (payload.reasoning.effort !== "high") {
              payload.reasoning.effort = "high";
              console.error("[jev-router] thinking escalated: reasoning.effort=high (prob " + thinkProb.toFixed(2) + ")");
            }
            escalated = true;
          }
          if (payload.thinking && typeof payload.thinking === "object") {
            if (payload.thinking.type && payload.thinking.type !== "enabled") {
              payload.thinking.type = "enabled";
              if (payload.thinking.budget_tokens === undefined) payload.thinking.budget_tokens = 16000;
              console.error("[jev-router] thinking escalated: thinking.type=enabled (prob " + thinkProb.toFixed(2) + ")");
            }
            escalated = true;
          }
          if (!escalated) {
            console.error("[jev-router] thinking escalation recommended (prob " + thinkProb.toFixed(2) + ") but payload has no thinking/reasoning parameter");
          }
        }
      }
    } catch (err) {
      console.error("[jev-router] error (fail open): " + (err.message || err));
    }
  });
}
