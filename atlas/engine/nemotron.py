"""Local Nemotron inference client (OpenAI-compatible) — the engine that replaces Copilot.

Talks to the local vLLM server serving Llama-3_3-Nemotron-Super-49B-v1_5. Endpoint config is
ENV-DRIVEN so the same app can point at local vLLM **or an NVIDIA NIM** with no code change:

    LLM_BASE_URL  (default http://localhost:8000/v1)
    LLM_MODEL     (default Llama-3_3-Nemotron-Super-49B-v1_5)
    LLM_API_KEY   (default "dummy" — vLLM ignores it; the SDK requires a value)

Nemotron quirks handled here (see ~/ATLAS/NEMOTRON_ARCHITECTURE.md):
- It ALWAYS wraps answers in <think>…</think> → strip_think() removes it.
- Greedy (temp=0) makes reasoning loop and blow the context budget → we use NVIDIA's
  recommended sampling temperature=0.6, top_p=0.95.
- The runtime context window (max_model_len) is read live from /models and used to budget
  max_tokens so prompt + reasoning + answer fit.
"""
from __future__ import annotations

import os
import re

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "Llama-3_3-Nemotron-Super-49B-v1_5")
LLM_API_KEY = os.getenv("LLM_API_KEY", "dummy")

_client = None
_ctx_window: int | None = None          # cached max_model_len from /models


class Cancelled(Exception):
    """Raised by complete() when should_cancel() goes true mid-generation — the Nemotron analog of
    closing a Copilot Chrome to abort the in-flight turn. The job worker maps this to 'interrupted'."""


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=600)
    return _client


def strip_think(text: str) -> str:
    """Remove Nemotron's <think>…</think> reasoning block; return the clean answer."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()


def est_tokens(text: str) -> int:
    """Cheap token estimate (~3.5 chars/token for English prose) — for budgeting, not exactness."""
    return int(len(text or "") / 3.5) + 1


def context_window(default: int = 8192) -> int:
    """Live max_model_len from the server (cached). Lets chunk/token budgeting auto-track 8K/32K/…"""
    global _ctx_window
    if _ctx_window is None:
        try:
            for m in _get_client().models.list().data:
                ml = getattr(m, "max_model_len", None)
                if ml:
                    _ctx_window = int(ml)
                    break
        except Exception:
            pass
        if _ctx_window is None:
            _ctx_window = default
    return _ctx_window


def health() -> dict:
    """Lightweight status for the reliability surface (model id + context window + reachability)."""
    try:
        data = _get_client().models.list().data
        m = data[0] if data else None
        return {"ok": True, "base_url": LLM_BASE_URL,
                "model": getattr(m, "id", LLM_MODEL),
                "max_model_len": getattr(m, "max_model_len", None)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "base_url": LLM_BASE_URL, "model": LLM_MODEL, "error": str(e)}


def complete(prompt: str, *, system: str = "detailed thinking off",
             temperature: float = 0.6, top_p: float = 0.95,
             max_tokens: int | None = None, retries: int = 2,
             on_log=None, should_cancel=None) -> str:
    """Single stateless completion. Returns the answer with the <think> block stripped.

    max_tokens defaults to (context_window - estimated prompt - margin), capped so a long
    reasoning trace + answer can't be requested beyond the window.

    If `should_cancel` (a no-arg callable) is supplied, the request is STREAMED and the flag is
    polled between chunks — when it goes true the stream is closed (vLLM stops generating, freeing
    the GPU) and `Cancelled` is raised. This is how the Working-on ✕ aborts an in-flight job.
    """
    win = context_window()
    if max_tokens is None:
        # est_tokens (3.5 chars/tok) UNDERcounts dense text (web sources, URLs, JSON), so pad the
        # prompt estimate before reserving the rest for output. The overflow self-correction below is
        # the hard guarantee if this still misjudges.
        budget = win - int(est_tokens(prompt) * 1.5) - est_tokens(system) - 256
        max_tokens = max(384, min(4500, budget))
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": prompt}]
    last = None
    for attempt in range(max(1, retries) + 2):       # +2 headroom to self-correct a context overflow
        try:
            if should_cancel is not None:
                return _complete_streaming(messages, temperature, top_p, max_tokens, should_cancel)
            r = _get_client().chat.completions.create(
                model=LLM_MODEL, messages=messages,
                temperature=temperature, top_p=top_p, max_tokens=max_tokens)
            return strip_think(r.choices[0].message.content)
        except Cancelled:
            raise                                    # user-initiated — never retry
        except Exception as e:  # noqa: BLE001
            last = e
            n = _ctx_overflow_tokens(e)              # server reported the real prompt size → fit to it
            if n is not None:
                max_tokens = max(256, min(max_tokens - 1, win - n - 96))
                if on_log:
                    on_log(f"[nemotron] context overflow — retrying with max_tokens={max_tokens}")
            elif on_log:
                on_log(f"[nemotron] attempt {attempt + 1} failed: {str(e)[:140]}")
    raise RuntimeError(f"Nemotron completion failed after {max(1, retries) + 2} attempt(s): {last}")


def _ctx_overflow_tokens(err) -> int | None:
    """If the server rejected the request for exceeding the context window, return the prompt's actual
    token count it reported (e.g. '… 4441 in the messages …') so we can shrink max_tokens to fit."""
    m = re.search(r"(\d+)\s+in the messages", str(err))
    return int(m.group(1)) if m else None


def _complete_streaming(messages, temperature, top_p, max_tokens, should_cancel) -> str:
    """Streamed completion that aborts promptly when should_cancel() goes true."""
    stream = _get_client().chat.completions.create(
        model=LLM_MODEL, messages=messages,
        temperature=temperature, top_p=top_p, max_tokens=max_tokens, stream=True)
    parts = []
    try:
        for chunk in stream:
            if should_cancel():
                raise Cancelled()
            delta = (chunk.choices[0].delta.content if chunk.choices else None) or ""
            if delta:
                parts.append(delta)
    finally:
        try:
            stream.close()                           # disconnect → vLLM stops generating
        except Exception:  # noqa: BLE001
            pass
    return strip_think("".join(parts))
