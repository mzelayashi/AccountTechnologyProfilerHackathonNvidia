"""Populate a customer's technology profile + overview + key contacts from their ATLAS trip
reports, using Copilot in WEB mode. Implements the ATP "context cassette" architecture: feed the
trip reports in ~20K-char chunks across ONE conversation (accumulating context), then run three
extraction turns over that context — technologies, overview, and contacts — in a single pass.
"""
from __future__ import annotations

import re

from atlas.atp import data_library, generations, profile_store, recency, topology_html
from atlas.engine.extract import extract_json
from atlas.store import customers

_CATS = ("datacenter", "networking", "security", "edge_iot")
CHUNK = 20000  # chars per conversation turn (Copilot Web input limit headroom)

# --- final extraction turns (operate over the trip reports already fed into the conversation) ---
TECH_PROMPT = (
    "Using ALL of the trip reports I shared above, list EVERY technology, product, platform, or "
    "vendor the customer uses, owns, is renewing, replacing, piloting, or evaluating (look "
    "especially at the Tech Profile Updates, Environment, Technical Notes, Initiatives, and "
    "Meeting Notes sections). Reply with a JSON array (no code fences); each item: "
    "vendor, product, category (datacenter|networking|security|edge_iot), deployment_status "
    "(active|legacy|planned|pilot|evaluation|unknown), model_number, version, specifications "
    "(object, e.g. renewal dates/terms/counts), notes. Infer category sensibly; if a need has no "
    "chosen vendor, skip it."
)
OVERVIEW_PROMPT = (
    "Using ALL of the trip reports above, write a business-focused technology overview of this "
    "customer for an executive/account manager. Reply with a JSON object (no code fences) with "
    "exactly these keys, each a 3-4 sentence paragraph specific to this customer (name real "
    "vendors, projects, and scale — no generic filler): "
    '{"workloads_hosting": "where workloads run (on-prem/cloud/hybrid), main compute/hosting '
    'platforms, scale", "applications_systems": "business applications, databases, critical '
    'systems discussed", "business_operations": "what business functions IT supports, industry/'
    'compliance drivers, main IT priorities and challenges"}.'
)
CONTACTS_PROMPT = (
    "Using ALL of the trip reports above (especially the ROLES sections), list the KEY CONTACTS — "
    "REAL human beings ONLY. EXCLUDE products, technologies, vendors-as-companies, and generic "
    "terms (e.g. Palo Alto, CrowdStrike, VMware, Business Review are NOT people). Merge duplicates "
    "and fix typos. Reply with a JSON array (no code fences); each item: "
    '{"name": "Full Name", "title": "job title (<=80 chars, empty if unknown)", "company": '
    '"their company", "is_customer": true for the customer’s employees, false for SHI/vendor}.'
)


def looks_complete(text: str) -> bool:
    """Accept predicate (used for EVERY turn of the chunked conversation, so it must handle both
    kinds of turn): a short 'OK part K' acknowledgement to a feed turn, OR a parseable, closed JSON
    array/object from an extraction turn. This lets Web Copilot complete each turn even when it
    omits the ATLAS-RESPONSE-COMPLETE marker (which it does nondeterministically). Stability (the
    answer must hold steady for a few polls) is enforced by the engine, so a loose match is safe."""
    t = (text or "").strip()
    low = t.lower()
    if len(t) <= 40 and "ok" in low and "part" in low:   # feed-turn ack: "OK part 3"
        return True
    if "]" not in t and "}" not in t:
        return False
    data = extract_json(t)
    return bool(data) and (isinstance(data, list) or isinstance(data, dict))


def _all_trip_text(customer: str) -> tuple[str, int]:
    d = customers.customer_dir(customer, create=False) / "trip_reports"
    if not d.exists():
        return "", 0
    parts, n = [], 0
    for p in sorted(d.glob("*")):
        if p.suffix.lower() in (".md", ".txt"):
            try:
                parts.append(f"===== TRIP REPORT: {p.name} =====\n{p.read_text(encoding='utf-8')}")
                n += 1
            except Exception:
                pass
    return "\n\n".join(parts), n


def _chunks(text: str, size: int = CHUNK) -> list[str]:
    """Split on whole-report boundaries, packing up to `size` chars per chunk; hard-split any
    single report that exceeds `size`."""
    reports = [r for r in re.split(r"(?=^===== TRIP REPORT:)", text, flags=re.M) if r.strip()]
    packed, cur = [], ""
    for r in reports:
        if cur and len(cur) + len(r) > size:
            packed.append(cur)
            cur = r
        else:
            cur += r
    if cur:
        packed.append(cur)
    out = []
    for c in packed:
        if len(c) <= size:
            out.append(c)
        else:
            out.extend(c[i:i + size] for i in range(0, len(c), size))
    return out


def _norm(s) -> str:
    return (str(s) if s is not None else "").strip().lower()


def _merge_techs(customer: str, items: list) -> tuple[int, int]:
    """Replace the trip-report-derived technologies with this fresh full extraction, preserving any
    the user added/edited by hand (source != 'trip_reports'). Because generate() always re-reads the
    WHOLE archive, a full replace makes re-running idempotent — Copilot's nondeterministic naming
    (e.g. 'Microsoft 365' vs 'Office 365') can't pile up near-duplicates run after run.
    Returns (kept_manual, generated)."""
    existing = data_library.load(customer)
    manual = [e for e in existing if _norm(e.get("source")) != "trip_reports"]
    taken = {(_norm(e.get("vendor")), _norm(e.get("product"))) for e in manual}
    generated, by_key = [], {}
    for it in items or []:
        if not isinstance(it, dict):
            continue
        vendor = (it.get("vendor") or "").strip()
        if not vendor:
            continue
        product = (it.get("product") or "").strip()
        key = (_norm(vendor), _norm(product))
        if key in taken:        # the user already curates this one by hand — don't shadow it
            continue
        cat = _norm(it.get("category"))
        cat = cat if cat in _CATS else "datacenter"
        status = _norm(it.get("deployment_status")) or "unknown"
        specs = it.get("specifications") if isinstance(it.get("specifications"), dict) else {}
        note = (it.get("notes") or "").strip()
        e = by_key.get(key)
        if e is None:           # dedupe within this single extraction by (vendor, product)
            e = {"vendor": vendor, "product": product, "category": cat,
                 "model_number": it.get("model_number") or "", "version": it.get("version") or "",
                 "specifications": dict(specs), "deployment_status": status,
                 "deployment_percentage": "", "satisfaction_level": "", "notes": note,
                 "source": "trip_reports"}
            generated.append(e)
            by_key[key] = e
        else:
            cur = e.get("specifications") if isinstance(e.get("specifications"), dict) else {}
            cur.update({k: v for k, v in specs.items() if v})
            e["specifications"] = cur
            if note and note not in (e.get("notes") or ""):
                e["notes"] = ((e.get("notes") or "") + (" " if e.get("notes") else "") + note).strip()
    data_library.save(customer, manual + generated)
    return len(manual), len(generated)


_OV_KEYS = ("workloads_hosting", "applications_systems", "business_operations")
_OV_LABELS = {
    "workloads_hosting": r"workloads?\s*(?:&|and)?\s*hosting",
    "applications_systems": r"applications?\s*(?:&|and)?\s*systems",
    "business_operations": r"business\s*operations",
}


def _parse_overview(text: str) -> dict:
    """The overview turn should return a JSON object, but Copilot occasionally answers in prose with
    bold section headers instead. Try JSON first, then fall back to splitting the prose on the three
    known section labels so a good answer is never silently dropped."""
    data = extract_json(text)
    if isinstance(data, dict):
        ov = {k: str(data[k]).strip() for k in _OV_KEYS if data.get(k)}
        if ov:
            return ov
    t = (text or "")
    if not t.strip():
        return {}
    # Fallback: find each label and take the text up to the next label.
    spans = []
    for key, lab in _OV_LABELS.items():
        m = re.search(lab, t, re.I)
        if m:
            spans.append((m.start(), m.end(), key))
    spans.sort()
    out = {}
    for i, (_s, e, key) in enumerate(spans):
        end = spans[i + 1][0] if i + 1 < len(spans) else len(t)
        body = t[e:end]
        body = re.sub(r"^[\s:*\-–—\"'>}]+", "", body)            # drop leading punctuation/markdown
        body = re.sub(r"[\s*\"',}]+$", "", body).strip()
        body = re.sub(r"\s*ATLAS-RESPONSE-COMPLETE\s*$", "", body).strip()
        if len(body) > 30:
            out[key] = body
    return out


def _clean_contacts(items: list, source: str | None = None) -> list:
    """Keep every real person Copilot returns — including first-name-only contacts like 'Claudia'
    or 'Richard'. We do NOT require a surname (the CONTACTS_PROMPT already excludes products/tech/
    vendors-as-companies), we only do light hygiene: drop blanks, trim, and dedupe.
    `source` tags provenance ("trip_reports" for generated, "manual" for hand-edited) so contacts
    can pin-and-merge like technologies; an existing source on the item is preserved when source is
    None."""
    out = []
    for c in items or []:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").strip()
        if not name:
            continue
        src = source if source is not None else (c.get("source") or "manual")
        out.append({"name": name, "title": (c.get("title") or "").strip()[:80],
                    "company": (c.get("company") or "").strip(),
                    "is_customer": bool(c.get("is_customer", True)), "source": src})
    # dedupe by lowercased (name, company) so the same first name at two companies both survive
    seen, uniq = set(), []
    for c in out:
        k = (c["name"].lower(), c["company"].lower())
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq


def _merge_contacts(customer: str, generated: list) -> int:
    """Pin-and-merge contacts (mirrors _merge_techs): keep the user's manual contacts
    (source != 'trip_reports'), then add generated ones whose (name, company) isn't already taken.
    Returns the count of generated contacts added."""
    existing = profile_store.load_contacts(customer)
    manual = [c for c in existing if _norm(c.get("source")) != "trip_reports"]
    taken = {(_norm(c.get("name")), _norm(c.get("company"))) for c in manual}
    added = []
    for c in generated or []:
        key = (_norm(c.get("name")), _norm(c.get("company")))
        if key in taken:
            continue
        taken.add(key)
        added.append(c)
    profile_store.save_contacts(customer, manual + added)
    return len(added)


_OV_FIELDS = ("workloads_hosting", "applications_systems", "business_operations")


def _merge_overview(customer: str, generated: dict) -> dict:
    """Pin-and-merge the overview per field: keep any paragraph the user pinned (listed in the
    stored '_manual'); fill the rest from the fresh generation. Returns the merged overview."""
    existing = profile_store.load_overview(customer)
    pinned = set(existing.get("_manual") or [])
    out = {}
    for k in _OV_FIELDS:
        if k in pinned and (existing.get(k) or "").strip():
            out[k] = existing[k]
        else:
            out[k] = generated.get(k) or existing.get(k) or ""
    out["_manual"] = sorted(pinned)
    profile_store.save_overview(customer, out)
    return out


def _dump_raw(customer: str, tech_a: str, ov_a: str, ct_a: str) -> None:
    """Persist the three raw extraction answers for debugging a parse miss."""
    try:
        p = customers.customer_dir(customer) / "account_technology_profile" / "_last_extract.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"===== TECHNOLOGIES =====\n{tech_a}\n\n===== OVERVIEW =====\n{ov_a}\n\n"
            f"===== CONTACTS =====\n{ct_a}\n", encoding="utf-8")
    except Exception:
        pass


def _synthesize_overview(ask, customer: str, per_chunk: list[dict]) -> dict:
    """Reduce step for the overview: merge the per-chunk overview JSONs into one (a small prompt
    that fits any window). Keeps OVERVIEW_PROMPT's schema."""
    import json
    blob = json.dumps(per_chunk, ensure_ascii=False)[:12000]
    prompt = (f"Below are partial technology-overview notes for {customer}, each a JSON object "
              "extracted from different sections of their trip reports:\n\n" + blob + "\n\n"
              "Merge them into ONE consolidated overview. Reply with a JSON object (no code fences) "
              'with exactly these keys, each a 3-4 sentence paragraph specific to this customer '
              '(name real vendors, projects, scale — no generic filler): '
              '{"workloads_hosting": "...", "applications_systems": "...", "business_operations": "..."}.')
    return _parse_overview(ask(prompt))


def generate_local(ask, customer: str, log=print) -> dict:
    """Map-reduce ATP generation for a finite-context LOCAL model (Nemotron). SAME prompts, parsing,
    merge, recency, persistence and snapshot as generate() — only the *feeding* differs: instead of
    one accumulating conversation (impossible under a local context window), extract per chunk and
    merge. `ask(prompt:str)->str` is a stateless single completion (e.g. nemotron.complete)."""
    import concurrent.futures as cf
    from atlas.engine import nemotron

    text, n_files = _all_trip_text(customer)
    if not text.strip():
        return {"ok": False, "error": "No trip reports filed for this customer yet.",
                "text": "No trip reports to read yet."}
    # Keep chunks SMALL: Nemotron's <think> block runs ~4-5K tokens, so each chunk's JSON answer must
    # stay short to finish within the 8K window. ~1500 chars/chunk → a short technology list that
    # completes (closed JSON) instead of truncating mid-array. More passes, but each one parses.
    chunk_chars = 1500
    chunks = _chunks(text, size=chunk_chars)
    log(f"Reading {n_files} trip report(s) in {len(chunks)} chunk(s) via local Nemotron "
        f"(map-reduce, {nemotron.context_window()}-token window)…")

    def _hdr(i, c):
        return f"These are SHI account trip-report excerpts for {customer} (part {i + 1} of {len(chunks)}).\n\n{c}\n\n"

    # MAP: run each chunk × each extraction prompt; concurrent (vLLM batches requests).
    tasks = []
    for i, c in enumerate(chunks):
        h = _hdr(i, c)
        tasks += [(i, "tech", h + TECH_PROMPT), (i, "overview", h + OVERVIEW_PROMPT),
                  (i, "contacts", h + CONTACTS_PROMPT)]

    def _run(t):
        i, kind, prompt = t
        try:
            return (i, kind, ask(prompt))
        except Exception as e:  # noqa: BLE001 — one bad pass shouldn't sink the whole run
            log(f"  pass failed (chunk {i + 1}/{len(chunks)}, {kind}): {str(e)[:80]}")
            return (i, kind, "")

    results, done = {}, 0
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for i, kind, ans in ex.map(_run, tasks):
            results[(i, kind)] = ans
            done += 1
            if done % 3 == 0 or done == len(tasks):
                log(f"  extracted {done}/{len(tasks)} passes…")

    # REDUCE — technologies (concat per-chunk lists; _merge_techs dedupes + preserves manual)
    all_techs = []
    for i in range(len(chunks)):
        d = extract_json(results.get((i, "tech"), ""))
        if isinstance(d, dict):
            d = d.get("technologies")
        if isinstance(d, list):
            all_techs.extend(d)
    kept, gen = _merge_techs(customer, all_techs)
    entries = data_library.load(customer)
    recency.assign(customer, entries)
    data_library.save(customer, entries)

    # REDUCE — contacts
    all_contacts = []
    for i in range(len(chunks)):
        d = extract_json(results.get((i, "contacts"), ""))
        if isinstance(d, list):
            all_contacts.extend(d)
    generated_contacts = _clean_contacts(all_contacts, source="trip_reports")
    n_added = _merge_contacts(customer, generated_contacts)

    # REDUCE — overview (1 chunk → use it; many → synthesize across them)
    per_overviews = [ov for i in range(len(chunks))
                     if (ov := _parse_overview(results.get((i, "overview"), "")))]
    if len(per_overviews) == 1:
        overview_raw = per_overviews[0]
    elif per_overviews:
        log("  synthesizing overview across chunks…")
        overview_raw = _synthesize_overview(ask, customer, per_overviews)
    else:
        overview_raw = {}
    overview = _merge_overview(customer, overview_raw) if overview_raw else profile_store.load_overview(customer)

    _dump_raw(customer, results.get((0, "tech"), ""), results.get((0, "overview"), ""),
              results.get((0, "contacts"), ""))

    uri = topology_html.write(customer)
    final_entries = data_library.load(customer)
    total = len(final_entries)
    merged_contacts = profile_store.load_contacts(customer)
    snap = generations.snapshot(customer, final_entries, overview, merged_contacts)
    has_ov = any((overview or {}).get(k) for k in _OV_FIELDS)
    log(f"{gen} technology(ies) from trip reports (+{kept} kept manual); +{n_added} new contact(s) "
        f"(now {len(merged_contacts)}); overview {'yes' if has_ov else 'no'}. "
        f"Saved as generation {snap['created_display']}.")
    return {"ok": True, "generated": gen, "kept": kept, "total": total,
            "contacts": len(merged_contacts), "overview": has_ov, "topology": uri,
            "generation": snap["id"], "generation_label": snap["created_display"],
            "text": f"Read {n_files} trip report(s) in {len(chunks)} chunk(s) via local Nemotron — "
                    f"{total} technology(ies) in the profile, {len(merged_contacts)} key contact(s), "
                    f"and a customer overview. Saved as generation {snap['created_display']}. "
                    f"Open the customer to view it."}


def generate(ask_chain_all, customer: str, log=print) -> dict:
    """`ask_chain_all(prompts)->list[answer]` must run in WEB mode. Feeds the trip reports in
    chunks across one conversation, then extracts technologies, overview, and contacts."""
    text, n_files = _all_trip_text(customer)
    if not text.strip():
        return {"ok": False, "error": "No trip reports filed for this customer yet.",
                "text": "No trip reports to read yet."}
    chunks = _chunks(text)
    log(f"Reading {n_files} trip report(s) in {len(chunks)} chunk(s) via Copilot (Web)…")
    feed = [f"These are the SHI account trip reports for {customer}, part {i + 1} of {len(chunks)}. "
            f"Read and remember them; don't analyze yet. Reply with: OK part {i + 1}.\n\n{c}"
            for i, c in enumerate(chunks)]
    answers = ask_chain_all(feed + [TECH_PROMPT, OVERVIEW_PROMPT, CONTACTS_PROMPT])
    if len(answers) < 3:
        return {"ok": False, "error": "Generation didn't complete.", "text": "Try again."}
    tech_a, ov_a, ct_a = answers[-3], answers[-2], answers[-1]
    _dump_raw(customer, tech_a, ov_a, ct_a)

    techs = extract_json(tech_a)
    techs = techs if isinstance(techs, list) else (techs.get("technologies") if isinstance(techs, dict) else [])
    kept, gen = _merge_techs(customer, techs or [])
    # Relevancy: count trip-report appearances + last-seen for every entry, then persist.
    entries = data_library.load(customer)
    recency.assign(customer, entries)
    data_library.save(customer, entries)

    overview_raw = _parse_overview(ov_a)
    overview = _merge_overview(customer, overview_raw) if overview_raw else profile_store.load_overview(customer)

    generated_contacts = _clean_contacts(
        extract_json(ct_a) if isinstance(extract_json(ct_a), list) else [], source="trip_reports")
    n_added = _merge_contacts(customer, generated_contacts)

    uri = topology_html.write(customer)
    final_entries = data_library.load(customer)
    total = len(final_entries)
    merged_contacts = profile_store.load_contacts(customer)
    snap = generations.snapshot(customer, final_entries, overview, merged_contacts)
    has_ov = any((overview or {}).get(k) for k in _OV_FIELDS)
    log(f"{gen} technology(ies) from trip reports (+{kept} kept manual); +{n_added} new contact(s) "
        f"(now {len(merged_contacts)}); overview {'yes' if has_ov else 'no'}. "
        f"Saved as generation {snap['created_display']}.")
    return {"ok": True, "generated": gen, "kept": kept, "total": total,
            "contacts": len(merged_contacts), "overview": has_ov, "topology": uri,
            "generation": snap["id"], "generation_label": snap["created_display"],
            "text": f"Read {n_files} trip report(s) in {len(chunks)} chunk(s) — {total} technology(ies) "
                    f"in the profile, {len(merged_contacts)} key contact(s), and a customer overview. "
                    f"Saved as generation {snap['created_display']}. Open the customer to view it."}
