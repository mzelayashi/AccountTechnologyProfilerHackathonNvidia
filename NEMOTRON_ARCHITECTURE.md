# NEMOTRON — Model Endpoint Architecture & Call Reference

**Single source of truth** for how this project talks to the local NVIDIA Nemotron model.
Every place that calls the LLM (the future replacement for the M365-Copilot/Selenium engine, and
later the SolutionEngineerTools AI calls) should follow exactly what is documented here.

> All facts below were **verified live** against the running server (`GET /v1/models` + real
> `chat/completions` calls). If the server is restarted with different settings, re-verify section 1.

---

## 1. Connection & credentials

| Item | Value |
|------|-------|
| **Base URL** | `http://localhost:8000/v1` |
| **API style** | OpenAI-compatible (served by **vLLM**) |
| **Model id** (exact, case-sensitive) | `Llama-3_3-Nemotron-Super-49B-v1_5` |
| **HuggingFace root** | `nvidia/Llama-3_3-Nemotron-Super-49B-v1_5` |
| **API key** | Any non-empty **dummy** string, e.g. `"not-needed"` or `"dummy"`. vLLM ignores it, but the OpenAI SDK requires *something*. |
| **Max context (`max_model_len`)** | **8192 tokens** — prompt **+** completion combined. Hard ceiling. |
| **Health / discovery** | `GET /v1/models` → returns the served model card (~0.4 s). Use as a readiness probe. |

Quick health check:
```bash
curl -s http://localhost:8000/v1/models
# -> {"object":"list","data":[{"id":"Llama-3_3-Nemotron-Super-49B-v1_5", ... "max_model_len":8192 ...}]}
```

---

## 2. ⚠️ THE critical quirk — strip `<think>…</think>` from every response

This is a **reasoning model**. The assistant's `content` is **always** prefixed with a
`<think>…</think>` block, and on this vLLM instance `reasoning_content` comes back **`null`**
(no server-side reasoning parser is splitting it out). Example raw `content`:

```
<think>\n\n</think>\n\nSDK OK
```

…and for harder prompts the `<think>` block can be hundreds of tokens of chain-of-thought.

**Therefore: every call site MUST strip the think block before using the text.** Use this canonical
helper (copy it into both repos — keep it identical):

```python
import re

def strip_think(text: str) -> str:
    """Remove Nemotron's <think>...</think> reasoning block, return the clean answer."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()
```

Gotchas:
- `"detailed thinking off"` **reduces but does not reliably eliminate** the inner reasoning for
  harder prompts — so stripping is mandatory **regardless of mode**.
- The reasoning tokens **count against the 8192 budget and add latency**. If you only need the answer,
  keep prompts in "off" mode and give enough `max_tokens` headroom that the real answer isn't cut off
  by a long think block (watch for `finish_reason: "length"`).

---

## 3. Reasoning mode toggle

Controlled by the **system message**:

| System message | Behavior | Recommended sampling (NVIDIA) |
|----------------|----------|-------------------------------|
| `detailed thinking off` | Terse / minimal reasoning. Default for extraction, classification, structured output. | Greedy: `temperature=0` |
| `detailed thinking on`  | Full chain-of-thought before the answer. Use for hard reasoning/planning. | `temperature=0.6, top_p=0.95` |

---

## 4. Call recipes (all confirmed working)

### 4a. curl — minimal chat completion
```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "Llama-3_3-Nemotron-Super-49B-v1_5",
    "messages": [
      {"role": "system", "content": "detailed thinking off"},
      {"role": "user",   "content": "What is 17*23? One line."}
    ],
    "temperature": 0,
    "max_tokens": 256
  }'
```

### 4b. OpenAI Python SDK — the path application code uses
```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed")

resp = client.chat.completions.create(
    model="Llama-3_3-Nemotron-Super-49B-v1_5",
    messages=[
        {"role": "system", "content": "detailed thinking off"},
        {"role": "user",   "content": "Reply with exactly: SDK OK"},
    ],
    temperature=0,
    max_tokens=1024,
)
answer = strip_think(resp.choices[0].message.content)   # <-- ALWAYS strip
print(answer)
```

### 4c. Streaming (standard OpenAI SSE)
```python
stream = client.chat.completions.create(
    model="Llama-3_3-Nemotron-Super-49B-v1_5",
    messages=[
        {"role": "system", "content": "detailed thinking off"},
        {"role": "user",   "content": "Say hi"},
    ],
    stream=True,
    max_tokens=64,
)
buf = []
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:
        buf.append(delta)
final = strip_think("".join(buf))   # <think> tokens stream too — strip after assembling
```

Raw SSE lines look like:
```
data: {"object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"<th"},"finish_reason":null}]}
data: [DONE]
```

### Response shape (non-streaming)
```jsonc
{
  "choices": [{
    "index": 0,
    "message": { "role": "assistant", "reasoning_content": null,
                 "content": "<think>...</think>\n\n<answer>", "tool_calls": [] },
    "finish_reason": "stop"          // or "length" if max_tokens was hit
  }],
  "usage": { "prompt_tokens": 23, "completion_tokens": 11, "total_tokens": 34 }
}
```

---

## 5. Constraints & integration notes (forward pointers)

- **8192-token ceiling.** ATLAS's Copilot-style prompts can be long — budget prompt + expected
  answer (+ any `<think>` overhead) under 8192, and trim/chunk where needed.
- **Local & unmetered.** No network egress, no rate limits, no real auth. Single model only.
- **Centralize config** so both repos read one place. Recommended env vars:
  ```
  NEMOTRON_BASE_URL=http://localhost:8000/v1
  NEMOTRON_MODEL=Llama-3_3-Nemotron-Super-49B-v1_5
  NEMOTRON_API_KEY=not-needed
  ```
- **ATLAS seam:** `config.py` already has an `LLM_PROVIDER` switch
  (`copilot` / `anthropic` / `azure_openai`). The next task adds a **`nemotron`** branch there.
- **Replacement target:** the engine swap will route these methods in
  `atlas/engine/copilot.py` to Nemotron instead of driving a browser:
  `Session.ask`, `Session.ask_chain`, `Session.ask_chain_all`, `Session.ask_at`.

---

_Verified on NVIDIA LaunchPad. Re-run section-1 checks if the vLLM server is relaunched with
different flags (model name, context length, or a reasoning parser would all change this doc)._
