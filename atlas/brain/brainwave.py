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
