// omp-jev-router — Jev context pruning + opt-in workhorse-first routing for omp.
// Hooks before_provider_request and per request:
//   1. Model routing (opt-in: JEV_ROUTE=1): every request starts on the
//      glm-5.3-flash workhorse. Escalation to the session's expert model
//      requires a deterministic struggle trigger (repeat tool calls, repeated tool
//      outputs, blockage language in the newest user message) AND — when
//      Jev is reachable — Jev's confirmation that the agent is genuinely
//      blocked, not just doing normal incremental work. Without a key or
//      an answer, the deterministic trigger decides alone. Signals
//      re-evaluate per request, so expert windows self-expire.
//   2. Context pruning (Jev): finds function_call_output items (tool
//      results), batch-evaluates relevance (one Noul question per chunk),
//      and replaces low-relevance outputs with placeholders.
//   3. Thinking escalation (Jev): difficulty probability > 0.7 raises the
//      payload's reasoning/thinking parameter when present, else logs a
//      recommendation to stderr.
//
// Env:
//   JEV_API_KEY    TypeSafe API key
//   JEV_THRESHOLD  prune when relevance probability < threshold [0.1]
//   JEV_MODE       "prune" (default) | "observe" | "off"
//   JEV_ROUTE      "1" enables workhorse-first model routing [off]

export default function (api) {
  console.error("[jev-router] extension loaded");
  var JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone";
  var THRESHOLD = parseFloat(process.env.JEV_THRESHOLD || "0.1");
  var MODE = process.env.JEV_MODE || "prune";
  var ROUTE = process.env.JEV_ROUTE === "1"; // routing off by default
  var MAX_CHARS = 6000;
  var evaluated = new Set();
  var pruned = new Set();

  var THINK_THRESHOLD = 0.7;
  // before_provider_request fires AFTER omp resolved the provider and
  // stripped its prefix: payload.model must be the provider-local ID
  // ("z-ai/glm-5.3-flash"), not omp's qualified "openrouter/z-ai/..."
  // form — OpenRouter rejects the 3-segment ID with a 400.
  var WORKHORSE_MODEL = "z-ai/glm-5.3-flash";
  var MAX_SUMMARY_CHARS = 4000;

  var STRUGGLE_WINDOW = 8; // recent items scanned for struggle signals
  var STRUGGLE_RE = /\b(still (broken|failing|not working|stuck|blocked)|not working|doesn'?t work|didn'?t work|same error|keeps? (failing|crashing|erroring|breaking)|no progress|you'?re (stuck|blocked)|blocked on|figure out why|why (is|does|do|won'?t)|no luck)\b/i;
  var LOOP_MIN = 2;  // identical tool+args calls inside the window
  var STUCK_MIN = 3; // identical tool outputs inside the window
  var CONFIRM_THRESHOLD = 0.5; // Jev noul below this vetoes escalation

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

  // Zero-API struggle detection: returns a short reason string when the
  // transcript shows the agent is blocked or struggling, else null.
  // Scans backwards from the newest item to the newest user message:
  //   - call loop: same tool + arguments issued twice in the window
  //   - stuck outputs: same tool result repeated 3x in the window
  //   - blockage language in the newest user message
  function detectStruggle(input) {
    var calls = [], outs = [], lastUser = "";
    for (var i = input.length - 1; i >= 0; i--) {
      var item = input[i];
      if (item.type === "function_call") {
        if (calls.length < STRUGGLE_WINDOW) {
          calls.push((item.name || "?") + " " + String(item.arguments || "").trim());
        }
      } else if (item.type === "function_call_output") {
        var o = typeof item.output === "string" ? item.output : "";
        if (o.length >= 8 && outs.length < STRUGGLE_WINDOW) outs.push({ h: hashContent(o), s: o.slice(0, 120).replace(/\s+/g, " ") });
      } else if (item.role === "user") {
        var c = item.content;
        lastUser = typeof c === "string" ? c : Array.isArray(c)
          ? c.filter(function(p) { return p.type === "input_text"; })
              .map(function(p) { return p.text || ""; }).join(" ")
          : "";
        break; // everything relevant sits after the newest user turn
      }
    }
    if (lastUser && STRUGGLE_RE.test(lastUser)) return "user blockage language";
    var sigs = {};
    for (var j = 0; j < calls.length; j++) {
      sigs[calls[j]] = (sigs[calls[j]] || 0) + 1;
      if (sigs[calls[j]] >= LOOP_MIN) return "repeat call: " + calls[j].slice(0, 120);
    }
    var outs2 = {};
    for (var k = 0; k < outs.length; k++) {
      outs2[outs[k].h] = (outs2[outs[k].h] || 0) + 1;
      if (outs2[outs[k].h] >= STUCK_MIN) return "repeated tool output: " + outs[k].s;
    }
    return null;
  }

  api.on("before_provider_request", async function (event) {
    if (MODE === "off") return;

    var payload = event.payload;
    if (!payload || !payload.input || !Array.isArray(payload.input)) return;

    // Model routing: workhorse by default; escalation needs a
    // deterministic struggle trigger, then Jev's final say below.
    // Expert = payload.model left untouched.
    var struggle = null;
    try { struggle = detectStruggle(payload.input); } catch (e) { struggle = null; }
    if (ROUTE && !struggle) {
      var prevModel = payload.model;
      payload.model = WORKHORSE_MODEL;
      console.error("[jev-router] route: workhorse (was " + prevModel + ")");
    }

    var apiKey = getApiKey();
    if (!apiKey) {
      if (ROUTE && struggle) console.error("[jev-router] route: keep expert " + payload.model + " (deterministic trigger, no Jev key: " + struggle + ")");
      return;
    }

    var query = extractQuery(payload.input);
    if (!query) return;

    var unevaluated = extractToolOutputs(payload.input);
    if (unevaluated.length > 0) unevaluated.forEach(function(c) { evaluated.add(c.hash); });

    try {
      // fan-out: state = query + summary + chunks; questions = one Noul
      // relevance question per chunk + thinking escalation
      var state = { user_query: query, conversation_summary: buildSummary(payload.input) };
      if (struggle) state.struggle_signals = struggle;
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

      questions.escalate_thinking = {
        type: "noul",
        instructions: "Does this turn involve a genuinely difficult problem that would benefit from extended thinking?"
      };
      if (ROUTE && struggle) {
        questions.confirm_struggle = {
          type: "noul",
          instructions: "A coding agent tripped this deterministic signal: '" + struggle + "'. Given the user query and conversation summary, is the agent genuinely blocked or struggling on a problem that needs a stronger model for this request? Normal incremental progress (reads, edits, rebuilds that change results) is not struggling."
        };
      }
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

      // escalation: deterministic trigger fired -> Jev has the final say.
      // A missing answer (API error) falls back to the trigger alone.
      if (ROUTE && struggle) {
        var conf = answers.confirm_struggle;
        if (conf && conf.noul !== undefined && conf.noul < CONFIRM_THRESHOLD) {
          var prevModel2 = payload.model;
          payload.model = WORKHORSE_MODEL;
          console.error("[jev-router] route: jev veto " + conf.noul.toFixed(2) + " < " + CONFIRM_THRESHOLD + " -> workhorse (was " + prevModel2 + ")");
        } else {
          console.error("[jev-router] route: expert kept " + payload.model + " (trigger: " + struggle + (conf && conf.noul !== undefined ? ", jev " + conf.noul.toFixed(2) : ", jev unavailable -> deterministic fallback") + ")");
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
