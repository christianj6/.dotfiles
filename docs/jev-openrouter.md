# Jev through OpenRouter

`config/omp/extensions/omp-jev-router.ts` calls Jev through OpenRouter's
decisions endpoint. The contract below was verified live on 2026-11-02; do not
re-derive it.

## Contract

| Part | Value |
| --- | --- |
| Endpoint | `POST https://openrouter.ai/api/alpha/decisions` |
| Auth | `Authorization: Bearer $OPENROUTER_API_KEY`, from the env or `~/.dotfiles/.env` |
| Model | `~typesafe/jev-latest`, which OpenRouter resolves to `typesafe/jev-1.14-20261014` |
| Body | `{"model", "state", "questions": {<key>: {"type": "noul", "instructions": <string>}}}` |
| Question types | `noul` (probability score), `choice`, `score`, `box` |
| Response | `{"model", "answers": {<key>: {"type": "noul", "noul": <0..1>}}, "usage", "provider": "TypeSafe"}` |

- **Wrong endpoints:** `/api/v1/chat/completions` refuses Jev with 400 ("a
  decisions model"), and `typesafe/jev-latest` without the `~` is not a valid id
  there.
- **`state` can be an object:** the spec gave it as a string, but the extension
  sends an object (`user_query`, `conversation_summary`, `chunk_<n>`), and that
  returned 200 with real scores.
- **Do not confuse it with `typesafe/jev-router`:** that is a different product.
  It routes chat requests to other models and returns no score.

## Live evidence

The owner's check: `state="agent read config.yml then edited it"` returned
`{"answers":{"relevant":{"type":"noul","noul":0.58}},"cost":0.0000118}`.

The extension's own code path, loaded by a Node harness with `JEV_MODE=observe`
and the key read from `~/.dotfiles/.env`:

    [jev-router] extension loaded
    HTTP 200 https://openrouter.ai/api/alpha/decisions model=~typesafe/jev-latest state=object questions=rel_0,rel_1,escalate_thinking
    RESPONSE {"model":"typesafe/jev-1.14-20261014","answers":{"rel_0":{"type":"noul","noul":0.98},"rel_1":{"type":"noul","noul":0.01},"escalate_thinking":{"type":"noul","noul":0.14}},"usage":{"input_tokens":591,"output_tokens":61,"cost":0.000024822},"id":"gen-dec-1793603509-Fca6MlGRAuoSRJZuRYPZ","provider":"TypeSafe"}
    [jev-router] pruned 1/2 tool outputs (threshold 0.1)

`rel_0` was a failing-test log for the query and `rel_1` an unrelated recipe;
only the recipe was pruned. The `HTTP` and `RESPONSE` lines come from the
harness, which wraps `fetch` to show what the extension sent and received.

Fail-open, with a bad key:

    HTTP 401 https://openrouter.ai/api/alpha/decisions ...
    RESPONSE {"error":{"message":"User not found.","code":401}}
    [jev-router] error (fail open): Jev API 401

The tool outputs were left untouched and the process exited 0.

## Open questions

Both are recorded as `TODO:` comments in the extension.

- **`JEV_MODE=observe` still prunes.** The observe run above pruned a chunk,
  because the code only checks for `"off"`. The owner decides what observe
  should mean.
- **The router may do nothing for the default model.** It only handles
  Responses-style payloads (`payload.input`). A one-shot omp session on
  `opencode-go/deepseek-v4.1-flash` (omp api `openai-completions`) loaded the
  extension and ran a tool, but made no Jev call. With a Responses payload,
  every turn with a user message calls Jev for `escalate_thinking`, so this
  points to an inert router, but it needs an instrumented check to confirm.
