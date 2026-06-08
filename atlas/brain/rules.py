"""The ATLAS Brain's operating rules — a user-editable 'constitution' the brain reads on every run.

Stored at vault/brain/brain_rules.md so the user can edit it (in Settings or directly on disk) to
'train' how the brain behaves. The default is seeded on first use. The brain injects these rules into
its customer-analysis and synthesis prompts.
"""
from __future__ import annotations

import config

RULES_PATH = config.VAULT_DIR / "brain" / "brain_rules.md"

DEFAULT_RULES = """# ATLAS Brain — Operating Rules

_Edit this file to train how the ATLAS brain works. It is read on every brainwave and injected into
the brain's prompts._

1. **The customer's own saved data is the #1 source.** Before anything else, read the customer's
   organized artifacts — their **trip reports** and **ATP technology profile**, filed under their
   folder. These are the ground truth. Never assume a customer's environment when we have it on file.
2. **Analyze saved data with the Web engine (fast).** The trip reports/artifacts are provided
   in-context, so reason over them in Copilot **Web** — no tenant round-trip needed.
3. **Use the Work engine only to check freshness / redundancy.** Confirm or add anything *recent*
   from live M365 (meetings, emails) that isn't already in the filed notes. Don't re-derive what we
   already have filed.
4. **Be specific to THIS customer.** Cite their real technologies, vendors, sites, and constraints by
   name (e.g. SentinelOne, their actual stack). No generic filler, no assumed profile.
5. **Be honest about gaps.** If the filed data doesn't cover something, say "not in filed notes" —
   never fabricate.
6. **Reuse what we already have.** Prefer existing artifacts, ATP profiles, and built-in skills over
   generating new work from scratch.
7. **Tie every conclusion to evidence.** Each point in the verdict should trace to a trip report, a
   known technology, or the product research.
"""


def load_rules() -> str:
    """Return the brain rules, seeding the default file on first use."""
    try:
        if RULES_PATH.exists():
            t = RULES_PATH.read_text(encoding="utf-8").strip()
            if t:
                return t
        RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        RULES_PATH.write_text(DEFAULT_RULES, encoding="utf-8")
    except Exception:
        pass
    return DEFAULT_RULES


def save_rules(text: str) -> str:
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_PATH.write_text((text or "").strip() or DEFAULT_RULES, encoding="utf-8")
    return load_rules()
