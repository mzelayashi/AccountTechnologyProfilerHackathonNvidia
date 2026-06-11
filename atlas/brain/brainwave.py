"""Brainwave — the first real fan-out of the ATLAS Brain (roadmap P2 + first slice of P3).

The "<product> a good fit for <customer>?" pattern. Instead of one shallow `ask`, the Brain:
  1. grounds on the customer's REAL data (ATP overview + technologies + recent trip reports),
  2. fans out two sub-agents in parallel — one **Web** instance researching the product, one **Work**
     instance analyzing the customer (tenant-grounded) — as background jobs,
  3. merges both into an ephemeral brainwave file, then
  4. synthesizes a grounded verdict on the facilitator thread, saved as a `brainwave` artifact.

This module holds the grounding + prompt builders; the orchestration (fan-out → wait → synthesize →
save) lives in JobManager._brainwave, which has the manager + a session.
"""
from __future__ import annotations

import re

from atlas.atp import data_library, profile_store, recency
from atlas.brain import rules as brain_rules
from atlas.store import customers, vault


def substantial(text: str) -> bool:
    """Accept predicate for the heavy sub-agents (research, saved-data analysis): a sizable prose
    answer is complete even when Copilot (esp. Web) forgets the marker. Engine still requires the
    answer to be STABLE for a few polls, so this can't fire on mid-stream chatter."""
    return len((text or "").strip()) > 400


def brief(text: str) -> bool:
    """Lenient accept for the live freshness check, which may legitimately be short ('nothing new')
    — so a brief valid answer completes instead of waiting out the timeout."""
    return len((text or "").strip()) > 80


def _norm(s: str) -> str:
    """Drop everything but letters/digits so 'ProPetro' == 'Pro_Petro' == 'Pro Petro'."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def resolve_customer(name: str) -> str | None:
    """Best-match a free-text name (e.g. 'ProPetro') to a real vault customer, tolerant of spaces,
    underscores, and casing."""
    target = _norm(name)
    if not target:
        return None
    rows = customers.list_customers()
    for r in rows:                                   # exact, separator-insensitive
        if _norm(r.get("name")) == target or _norm(r.get("slug")) == target:
            return r["name"]
    for r in rows:                                   # substring either direction
        n = _norm(r.get("name"))
        if n and (target in n or n in target):
            return r["name"]
    return None


def _atp_summary(customer: str) -> str:
    parts = []
    ov = profile_store.load_overview(customer)
    for k, lab in (("workloads_hosting", "Workloads & Hosting"),
                   ("applications_systems", "Applications & Systems"),
                   ("business_operations", "Business Operations")):
        if ov.get(k):
            parts.append(f"{lab}: {ov[k]}")
    techs = data_library.load(customer)
    if techs:
        lines = [f"- {(e.get('vendor') or '')}{' / ' + e['product'] if e.get('product') else ''} "
                 f"({e.get('category', '')}, {e.get('deployment_status', '')})" for e in techs[:60]]
        parts.append("Known technologies (from ATP profile):\n" + "\n".join(lines))
    return "\n\n".join(parts).strip()


def customer_saved_text(customer: str, cap: int = 120000) -> tuple[str, int, int]:
    """The customer's OWN organized data — ATP profile + the actual trip-report CONTENT, most recent
    first. This is the brain's #1 source. Large sets are fed in chunks (see saved_feed_prompts), so
    the cap is generous. Returns (text, reports_used, reports_total)."""
    parts = []
    atp = _atp_summary(customer)
    if atp:
        parts.append("=== ATP TECHNOLOGY PROFILE ===\n" + atp)
    d = customers.customer_dir(customer, create=False) / "trip_reports"
    files = sorted([p for p in d.glob("*") if p.suffix.lower() in (".md", ".txt")], reverse=True) \
        if d.exists() else []
    used = sum(len(p) for p in parts)
    n = 0
    for p in files:
        try:
            chunk = f"===== TRIP REPORT: {p.name} =====\n{p.read_text(encoding='utf-8')}"
        except Exception:
            continue
        if used + len(chunk) > cap and n > 0:
            break
        parts.append(chunk)
        used += len(chunk)
        n += 1
    return "\n\n".join(parts).strip(), n, len(files)


def research_prompt(product: str, question: str) -> str:
    return (f"Research **{product}** for an enterprise B2B buyer (context: {question}). Cover, "
            f"specifically and factually: what it is and its core architecture; deployment model "
            f"(cloud / on-prem / hybrid) and dependencies; key strengths; limitations and risks; the "
            f"main competitors and how {product} compares; typical pricing/licensing model; and which "
            f"customer profiles it fits best vs poorly. Be concrete — no marketing filler.")


def feed_or_substantial(text: str) -> bool:
    """Accept predicate for the chunked saved-data feed: a short 'OK part K' ack, OR a substantial
    final analysis. Lets the conversation complete even when Web drops the marker."""
    s = (text or "").strip()
    if len(s) > 400:
        return True
    low = s.lower()
    return len(s) <= 40 and "ok" in low and "part" in low


def _analysis_instruction(customer: str, product: str, question: str) -> str:
    return (f"{brain_rules.load_rules()}\n\n"
            f"Using ALL of {customer}'s saved data above (our filed trip reports + ATP profile — per "
            f"Rule 1 this is the ground truth), summarize {customer}'s actual environment relevant to "
            f"evaluating **{product}** (context: {question}). Cite specifics from the notes: their "
            f"current relevant technologies & vendors (name them); sites/footprint; security & "
            f"compliance posture; initiatives & pain points; and constraints. For anything not "
            f"covered, write 'not in filed notes'. Do not invent details.")


def saved_customer_prompt(customer: str, product: str, question: str, saved_text: str) -> str:
    """Single-turn variant (small saved sets)."""
    data = (saved_text or "").strip() or "(no saved trip reports or profile on file for this customer.)"
    return f"{_analysis_instruction(customer, product, question)}\n\n=== {customer} SAVED DATA ===\n{data}"


def saved_feed_prompts(customer: str, product: str, question: str, saved_text: str) -> list[str]:
    """Chunk the saved data across one Web conversation (feed turns), then ask for the analysis — so
    ALL of the customer's trip reports are read even when they're large."""
    from atlas.atp.extract import _chunks
    chunks = _chunks(saved_text or "", 24000)   # bigger chunks = fewer Web turns = faster
    feed = [f"This is {customer}'s saved account data, part {i + 1} of {len(chunks)}. Read and "
            f"remember it; reply only: OK part {i + 1}.\n\n{c}" for i, c in enumerate(chunks)]
    return feed + [_analysis_instruction(customer, product, question)]


def redundancy_prompt(customer: str, product: str, question: str) -> str:
    """A live-tenant freshness/redundancy check (Work mode)."""
    return (f"{brain_rules.load_rules()}\n\n"
            f"Per Rule 3, this is a FRESHNESS check. Using our live M365 data (recent meetings, "
            f"emails, chats) for **{customer}**, what is the LATEST relevant to evaluating "
            f"**{product}** (context: {question})? Focus on anything RECENT or new that may not be in "
            f"older filed trip reports — current initiatives, recent conversations, decisions, or "
            f"changes. Be brief and flag what's new. If nothing recent is found, say so plainly.")


def research_prompt_web(product: str, question: str, sources: str) -> str:
    """Nemotron research agent, grounded on LIVE web SOURCES (DuckDuckGo). Falls back to model
    knowledge (flagged) when the web is unreachable."""
    if (sources or "").strip():
        return (f"You are a product-research analyst. Using the live web SOURCES below, research "
                f"**{product}** for an enterprise B2B buyer (context: {question}). Cover, factually: "
                f"what it is and its current product line / latest models; deployment model (cloud / "
                f"on-prem / hybrid) and dependencies; key strengths; limitations and risks; main "
                f"competitors and how {product} compares; and which customer profiles it fits best vs "
                f"poorly. Cite sources inline as [n]. Note the information is current as of today. Be "
                f"concrete — no marketing filler.\n\n=== WEB SOURCES ===\n{sources[:6000]}")
    return (f"You are a product-research analyst. Live web search was unavailable, so use your own "
            f"knowledge and clearly note it may not reflect the very latest releases. Research "
            f"**{product}** for an enterprise B2B buyer (context: {question}): what it is and its "
            f"product line; deployment model and dependencies; strengths; limitations and risks; main "
            f"competitors and how it compares; and the customer profiles it fits best vs poorly. Be "
            f"concrete — no marketing filler.")


def web_research_prompt(topic: str, sources: str) -> str:
    """Standalone web-research brief (no customer) — the research agent run on its own when the user
    asks to research/look up an external topic. Grounded on live web SOURCES, falls back to model
    knowledge (flagged) when the web is unreachable."""
    if (sources or "").strip():
        return (f"You are a research analyst. Using ONLY the live web SOURCES below, write a clear, "
                f"factual markdown brief on:\n\n**{topic}**\n\nCover the concrete specifics (what it is, "
                f"the current/latest options or models, how they differ, notable changes, and practical "
                f"considerations). Cite sources inline as [n]. Note the information is current as of "
                f"today. No marketing filler.\n\n=== WEB SOURCES ===\n{sources[:6000]}")
    return (f"You are a research analyst. Live web search was unavailable, so use your own knowledge and "
            f"clearly note it may not reflect the very latest. Write a clear, factual markdown brief on: "
            f"**{topic}**.")


def synth_prompt_local(product: str, customer: str, question: str,
                       research: str, saved: str) -> str:
    """The synthesis ('third agent') for Nemotron — tightly capped to fit the 8K window with room for
    a full 4-section verdict. No live-tenant section (no M365 on this engine)."""
    return (f"{brain_rules.load_rules()}\n\n"
            f"You advise an SHI Solutions Architect. Decide whether **{product}** is a good fit for "
            f"**{customer}**, grounded FIRST in their saved data (Rule 1). Original ask: \"{question}\".\n\n"
            f"=== PRODUCT RESEARCH (from live web): {product} ===\n{(research or '(none)')[:3500]}\n\n"
            f"=== {customer} — FROM OUR SAVED TRIP REPORTS / PROFILE (PRIMARY) ===\n"
            f"{(saved or '(none)')[:3500]}\n\n"
            f"Write in markdown, specific to {customer}, citing their real technologies/sites by name:\n"
            f"## Verdict\ngood fit / conditional fit / poor fit — decisive reasons tied to {customer}'s "
            f"actual stack, sites, and constraints.\n"
            f"## Where it fits\nconcrete opportunities in their environment.\n"
            f"## Risks &amp; objections for {customer}\nand how to handle them.\n"
            f"## Recommended next step\nwhat you'd do or propose next.\n\n"
            f"Avoid generic filler. If the saved data is thin, say so plainly.")


def verify_prompt(product: str, customer: str, verdict: str,
                  research: str, saved: str) -> str:
    """The self-check ('fourth agent'): the brain audits its own verdict against the evidence before
    the receipt is finalized. Returns JSON the orchestrator parses with extract_json."""
    return (f"You are a meticulous fact-checker auditing an analyst's verdict on whether **{product}** "
            f"fits **{customer}**. Check each claim in the VERDICT against the EVIDENCE. Flag (a) any "
            f"claim about {customer}'s environment/stack NOT supported by their saved data, and (b) any "
            f"claim about {product} NOT supported by the research. Do not add new opinions.\n\n"
            f"=== VERDICT UNDER REVIEW ===\n{(verdict or '')[:3500]}\n\n"
            f"=== EVIDENCE: {customer} saved data ===\n{(saved or '(none)')[:2500]}\n\n"
            f"=== EVIDENCE: {product} research ===\n{(research or '(none)')[:2500]}\n\n"
            f"Reply with ONLY JSON: {{\"consistent\": true|false, \"confidence\": \"high\"|\"medium\""
            f"|\"low\", \"issues\": [\"<unsupported or contradicted claim>\", ...], \"note\": \"<one-"
            f"sentence overall assessment>\"}}")


def synth_prompt(product: str, customer: str, question: str,
                 research: str, saved: str, live: str) -> str:
    return (f"{brain_rules.load_rules()}\n\n"
            f"You advise an SHI Solutions Architect. Decide whether **{product}** is a good fit for "
            f"**{customer}**, grounded FIRST in their saved data (Rule 1). Original ask: "
            f"\"{question}\".\n\n"
            f"=== PRODUCT RESEARCH: {product} ===\n{(research or '(none)')[:7000]}\n\n"
            f"=== {customer} — FROM OUR SAVED TRIP REPORTS / PROFILE (PRIMARY) ===\n"
            f"{(saved or '(none)')[:8000]}\n\n"
            f"=== {customer} — LIVE M365 FRESHNESS CHECK (secondary) ===\n{(live or '(none)')[:4000]}\n\n"
            f"Write in markdown, specific to {customer}, citing their real technologies/sites by name:\n"
            f"## Verdict\ngood fit / conditional fit / poor fit — with the decisive reasons tied to "
            f"{customer}'s actual stack, sites, and constraints.\n"
            f"## Where it fits\nconcrete opportunities in their environment.\n"
            f"## Risks &amp; objections for {customer}\nand how to handle them.\n"
            f"## Recommended next step\nwhat you'd do or propose next.\n\n"
            f"Avoid generic filler. If the saved data is thin, say so and lean on the freshness check.")
