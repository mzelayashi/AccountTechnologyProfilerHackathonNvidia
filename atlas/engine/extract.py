"""Pull structured data out of Copilot's free-form answers."""
from __future__ import annotations

import json
import re


def extract_json(raw: str) -> dict | list | None:
    """Best-effort JSON from a Copilot answer (handles ```json fences / stray prose)."""
    if not raw:
        return None
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        s, e = raw.find(opener), raw.rfind(closer)
        if s != -1 and e > s:
            try:
                return json.loads(raw[s : e + 1])
            except json.JSONDecodeError:
                continue
    return None
