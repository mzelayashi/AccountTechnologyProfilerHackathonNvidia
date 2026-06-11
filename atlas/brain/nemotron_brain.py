"""Nemotron-powered ATLAS Brain.

Routes a free-text command to one of:
  - run_skill : launch a customer-scoped skill (strategic_briefing, account_360, …) as a job
  - navigate  : an interactive skill (SEdraw network/vision, People Resources) → tell the user to use Skills
  - rag       : answer a question by searching the Customer Vault (one customer, several, or ALL) and
                synthesizing a cited answer with the local Nemotron model.

Reuses brainwave.resolve_customer / customer_saved_text and the local nemotron engine.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from atlas.brain import brainwave as bw
from atlas.engine import nemotron
from atlas.engine.extract import extract_json
from atlas.store import customers

# Skills the Brain can auto-run for a single customer on Nemotron (grounded on saved data).
RUNNABLE = {
    "strategic_briefing": "Deep strategic account briefing (initiatives, opportunities, risks, talking points).",
    "account_360": "One-page 360° snapshot of the account.",
    "battlecard": "Competitive battlecard for the account.",
    "whitespace": "Whitespace / upsell opportunities for the account.",
    "follow_up": "Action items + a follow-up email from the account's latest meeting.",
    "environment_topology": "Map the customer's technology environment to a topology diagram.",
}
NOINPUT = {
    "daily_briefing": "Today's meetings briefing.",
    "knowledge_drop": "Ingest and file inbox documents.",
}
# Interactive skills — the Brain must NOT auto-run these; it points the user to the Skills page.
NAVIGATE = {
    "sedraw_network": "SEdraw Network Diagrams",
    "sedraw_vision": "SEdraw Vision Boards",
    "find_resource": "People Resources",
}


def saved_context(customer: str, cap_chars: int = 7500) -> str:
    """The customer's saved data (ATP profile + recent trip reports), HARD-capped to fit the 8K context
    window with room left for the skill's prompt + reasoning + JSON output — prefixed onto a skill's
    prompt so Copilot-era skills work grounded on Nemotron."""
    if not customer:
        return ""
    try:
        text, _used, _total = bw.customer_saved_text(customer, cap=cap_chars)
    except Exception:
        return ""
    if not text:
        return ""
    # customer_saved_text always includes the ATP profile + the most-recent report even past the cap,
    # so it can overshoot — hard-truncate to keep the model's output budget intact.
    if len(text) > cap_chars:
        text = text[:cap_chars] + "\n…(saved data truncated to fit the context window)…"
    return (f"You have NO live access to this customer's systems. Use ONLY the saved account data below "
            f"to answer. If something isn't in it, say so.\n\n=== {customer} SAVED ACCOUNT DATA ===\n"
            f"{text}\n\n=== END SAVED DATA ===\n\n")


# --------------------------------------------------------------------------- routing
def _route_prompt(text: str, names: list[str]) -> str:
    runnable = "\n".join(f"- {k}: {v}" for k, v in RUNNABLE.items())
    nav = "\n".join(f"- {k}: {v}" for k, v in NAVIGATE.items())
    sample = ", ".join(names[:60])
    return f"""You are the router for an account-intelligence app. Decide what the user wants and reply with ONLY a JSON object (no prose, no code fences).

RUNNABLE SKILLS (each runs for ONE customer):
{runnable}

INTERACTIVE SKILLS (cannot run from the command box — the user must open the Skills page and follow prompts):
{nav}

KNOWN CUSTOMERS (sample): {sample}

Return JSON:
{{"action": "run_skill" | "navigate" | "rag" | "brainwave" | "research", "skill": "<skill key or empty>", "customer": "<customer name or empty>", "product": "<product/vendor, for brainwave>", "topic": "<what to research, for research>", "question": "<the question, for rag>"}}

RULES:
- If the user asks whether a PRODUCT/VENDOR is a good fit for a customer, or to evaluate / assess / weigh adopting one (e.g. "is Palo Alto a good fit for Acme", "should Acme buy CrowdStrike", "would Zscaler work for Acme", "evaluate Fortinet for Acme") -> action=brainwave, product=<product/vendor>, customer=<name>.
- If the user asks to RESEARCH / look up / find the LATEST on an EXTERNAL topic, product, vendor or technology that is NOT about their own customers (e.g. "research the latest Palo Alto firewalls", "what's new with Zscaler", "look up CrowdStrike Falcon pricing", "latest NVIDIA GPUs") -> action=research, topic=<what to research>. This goes to the WEB.
- If the user asks to RUN a runnable skill for a customer (e.g. "strategic briefing for Acme", "battlecard on Acme") -> action=run_skill, skill=<key>, customer=<name>.
- If the user asks to create a network diagram or vision board, or to find a person/engineer/resource -> action=navigate, skill=<the interactive key>.
- If the user ASKS A QUESTION about THEIR OWN customers, the customers' existing technology/vendors, or what's in the vault (e.g. "which customers use Palo Alto", "does Acme use CrowdStrike") -> action=rag, question=<the question>.
- Disambiguate carefully: "research/latest/look up <product>" (external, no specific customer) -> research (WEB). "which customers use <product>" / "does <customer> use <product>" -> rag (VAULT lookup). "is <product> a good fit for <customer>" -> brainwave.
- When unsure between research and rag: if it names one of the customers above or asks "which/my customers", choose rag; otherwise choose research.

USER REQUEST: {text}
JSON:"""


def route(text: str, on_log=None, should_cancel=None) -> dict:
    text = (text or "").strip()
    if not text:
        return {"action": "rag", "question": ""}
    names = [c.get("name", "") for c in customers.list_customers()]
    try:
        raw = nemotron.complete(_route_prompt(text, names), max_tokens=400, on_log=on_log,
                                should_cancel=should_cancel)
        d = extract_json(raw) or {}
    except nemotron.Cancelled:
        raise
    except Exception as e:  # noqa: BLE001
        if on_log:
            on_log(f"[brain] route failed ({e}); defaulting to RAG.")
        d = {}
    action = d.get("action") if isinstance(d, dict) else None
    skill = (d.get("skill") or "").strip() if isinstance(d, dict) else ""
    cust = (d.get("customer") or "").strip() if isinstance(d, dict) else ""
    prod = (d.get("product") or "").strip() if isinstance(d, dict) else ""
    topic = (d.get("topic") or "").strip() if isinstance(d, dict) else ""
    if action == "research" and (topic or prod):
        return {"action": "research", "topic": topic or prod}
    if action == "brainwave" and prod:
        return {"action": "brainwave", "product": prod, "customer": bw.resolve_customer(cust) or cust}
    if action == "run_skill" and skill in RUNNABLE:
        return {"action": "run_skill", "skill": skill, "customer": bw.resolve_customer(cust) or cust}
    if action == "navigate" and skill in NAVIGATE:
        return {"action": "navigate", "skill": skill}
    # default: RAG
    return {"action": "rag", "question": d.get("question") if isinstance(d, dict) and d.get("question") else text}


# --------------------------------------------------------------------------- RAG
_STOP = {"the", "a", "an", "of", "do", "does", "is", "are", "use", "uses", "using", "have", "has",
         "which", "what", "who", "any", "all", "my", "our", "customers", "customer", "and", "or",
         "with", "for", "in", "on", "at", "to", "their", "they", "currently", "right", "now", "me",
         "tell", "show", "list", "check", "if", "found", "go", "through", "details", "give"}


def _scope_prompt(question: str, names: list[str]) -> str:
    sample = ", ".join(names[:80])
    return f"""From the question, extract JSON (only JSON):
{{"scope": "all" | "named", "customers": ["<name>", ...], "terms": ["<key product/vendor/tech term>", ...]}}

- scope="all" when it asks across all/which/any customers; scope="named" when it targets specific customer(s).
- customers: the customer name(s) mentioned (use names close to this list when possible): {sample}
- terms: the concrete things to search for (vendors, products, technologies) — lowercase, no filler.

QUESTION: {question}
JSON:"""


def _parse_scope(question: str, on_log=None, should_cancel=None) -> tuple[list[str], list[str]]:
    names = [c.get("name", "") for c in customers.list_customers()]
    scope, raw_customers, terms = "all", [], []
    try:
        d = extract_json(nemotron.complete(_scope_prompt(question, names), max_tokens=300,
                                           on_log=on_log, should_cancel=should_cancel)) or {}
    except nemotron.Cancelled:
        raise
        scope = (d.get("scope") or "all").lower()
        raw_customers = [str(x) for x in (d.get("customers") or []) if str(x).strip()]
        terms = [str(x).strip().lower() for x in (d.get("terms") or []) if str(x).strip()]
    except Exception:
        pass
    # fallback terms: salient words from the question
    if not terms:
        terms = [w for w in re.findall(r"[A-Za-z0-9.\-]{3,}", question.lower()) if w not in _STOP][:6]
    # resolve scope → concrete customer list
    if scope == "named" and raw_customers:
        resolved = [bw.resolve_customer(c) for c in raw_customers]
        scoped = [r for r in resolved if r]
        if scoped:
            return scoped, terms
    return names, terms                       # default: ALL customers


def _match(text: str, terms: list[str]) -> bool:
    t = (text or "").lower()
    return any(term in t for term in terms)


def _search_customer(name: str, terms: list[str], per_source_cap: int = 4) -> list[dict]:
    """Deterministic search across a customer's vault data. Returns hit dicts (bounded)."""
    from atlas.atp import data_library, profile_store
    from atlas.store import artifacts as art_store
    hits: list[dict] = []
    cdir = customers.customer_dir(name, create=False)

    # 1) ATP tech inventory (the structured "who uses X" signal)
    try:
        for e in data_library.load(name):
            blob = " ".join(str(e.get(k, "")) for k in ("vendor", "product", "category", "notes")) \
                + " " + json.dumps(e.get("specifications") or {})
            if _match(blob, terms):
                hits.append({"source": "ATP tech profile",
                             "detail": f"{e.get('vendor','')} {e.get('product','')}".strip()
                                       + f" — {e.get('deployment_status','')}"
                                       + (f"; {e.get('notes','')}" if e.get("notes") else "")})
    except Exception:
        pass

    # 2) trip reports (match lines)
    try:
        d = cdir / "trip_reports"
        for p in sorted(d.glob("*.md"))[:50] if d.exists() else []:
            lines = [ln.strip() for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if _match(ln, terms)]
            if lines:
                hits.append({"source": f"trip report {p.name}", "detail": " … ".join(lines[:3])[:400]})
    except Exception:
        pass

    # 3) overview
    try:
        ov = profile_store.load_overview(name)
        for k in ("workloads_hosting", "applications_systems", "business_operations"):
            if _match(ov.get(k, ""), terms):
                hits.append({"source": "overview", "detail": ov[k][:300]})
    except Exception:
        pass

    # 4) vision / network Excel inputs + drawio outputs
    try:
        import openpyxl
        for sub in ("vision_input", "network_input"):
            for p in sorted((cdir / sub).glob("*.xlsx")) if (cdir / sub).exists() else []:
                try:
                    wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
                    cells = [str(c.value) for ws in wb.worksheets for row in ws.iter_rows()
                             for c in row if c.value is not None]
                    if any(_match(v, terms) for v in cells):
                        kind = "vision board" if sub == "vision_input" else "network diagram"
                        hits.append({"source": f"{kind} ({p.name})",
                                     "detail": "; ".join(v for v in cells if _match(v, terms))[:300]})
                except Exception:
                    pass
    except Exception:
        pass

    # 5) filed artifacts for this customer
    try:
        for a in art_store.list_all():
            if (a.get("customer") or "") == name and _match(a.get("text", ""), terms):
                hits.append({"source": f"artifact: {a.get('title','')}", "detail": a.get("skill_name", "")})
    except Exception:
        pass

    return hits[:per_source_cap * 3]


def _synth_prompt(question: str, evidence: str) -> str:
    return f"""You are an account-intelligence analyst. Answer the user's question using ONLY the evidence found in the customer vault below. Be specific and cite where each fact came from (which customer, and which trip report / ATP profile / vision board / network diagram / artifact). If nothing relevant was found, say so plainly.

IMPORTANT: each evidence block is headed by "## <Customer Name>". That header is the AUTHORITATIVE customer identity — attribute every fact under it to that customer, even if the body text mentions a different company name. Do NOT claim evidence belongs to a different customer based on names inside the text.

QUESTION: {question}

EVIDENCE (search hits from the vault):
{evidence if evidence.strip() else "(no matches found in any customer's data)"}

Write a concise, well-structured markdown answer. For "which customers" questions, give a bullet per matching customer with where it was found. For a single-customer question, state yes/no and list each place it appears with brief detail."""


def rag_answer(question: str, on_log=None, should_cancel=None) -> dict:
    question = (question or "").strip()
    if not question:
        return {"text": "Ask a question about your customers (e.g. \"which customers use Palo Alto?\")."}
    scoped, terms = _parse_scope(question, on_log, should_cancel)
    if on_log:
        on_log(f"🧠 Searching {len(scoped)} customer(s) for: {', '.join(terms) or '(question terms)'}…")
    # Retrieve (cooperative cancel: the ✕ stops a long all-customers scan promptly)
    found = []  # (customer, [hits])
    for name in scoped:
        if should_cancel and should_cancel():
            raise nemotron.Cancelled()
        hits = _search_customer(name, terms)
        if hits:
            found.append((name, hits))
    if on_log:
        on_log(f"🧠 Matches in {len(found)} customer(s). Synthesizing…")
    # Build bounded evidence text
    found = found[:30]
    lines = []
    for name, hits in found:
        lines.append(f"## {name}")
        for h in hits[:6]:
            lines.append(f"- [{h['source']}] {h['detail']}")
    evidence = "\n".join(lines)[:7000]
    answer = nemotron.complete(_synth_prompt(question, evidence), max_tokens=1800, on_log=on_log,
                               should_cancel=should_cancel)
    if not (answer or "").strip():
        # deterministic fallback if the model returns nothing
        if not found:
            answer = f"No customers in the vault have data matching **{', '.join(terms) or question}**."
        else:
            answer = "**Found in:**\n" + "\n".join(
                f"- **{n}** — " + "; ".join(h["source"] for h in hs[:4]) for n, hs in found)
    return {"text": answer, "matches": len(found), "searched": len(scoped)}
