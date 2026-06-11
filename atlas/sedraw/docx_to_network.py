"""Convert a Word (.docx) network/TD intake into the SEdraw network-topology structure with the local
Nemotron model — a best-effort map onto the Excel intake schema the network generator already consumes.

Pipeline (driven by service.convert_docx_network):
    .docx → extract_text() → parse_to_network() (Nemotron) → {"sites":[…]} → _clean_network →
    write_network_topology (.xlsx) → generate_network (.drawio + viewer)

Not everything in a Word doc maps cleanly; the model maps what it can and omits the rest. The user can
then edit the generated intake .xlsx in the GUI editor and regenerate.
"""
from __future__ import annotations

from pathlib import Path

from atlas.engine import nemotron
from atlas.engine.extract import extract_json
from atlas.sedraw import constants as C

_CAP = 11000  # chars of doc text fed to the model (after placeholder stripping; leaves room for output)

# Empty Word form-field / content-control placeholders — pure noise, dropped from the extract.
_PLACEHOLDERS = ("click or tap here to enter text.", "click or tap to enter a date.",
                 "click or tap here to enter a date.", "choose an item.", "enter text.")


def _el_text(el) -> str:
    """ALL text under an element IN DOCUMENT ORDER — including text inside content controls (w:sdt)
    and form fields that python-docx's .text skips, whether or not they're wrapped in paragraphs. A
    newline is inserted at each paragraph boundary so lines stay separated; tabs/breaks → spaces."""
    from docx.oxml.ns import qn
    T, TAB, BR, CR, PARA = qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr"), qn("w:p")
    parts = []
    for node in el.iter():
        if node.tag == T:
            parts.append(node.text or "")
        elif node.tag in (TAB, BR, CR):
            parts.append(" ")
        elif node.tag == PARA:
            parts.append("\n")
    return "".join(parts)


def _strip_ph(s: str) -> str:
    import re
    for ph in _PLACEHOLDERS:
        s = re.sub(re.escape(ph), "", s, flags=re.I)
    return re.sub(r"[ \t]{2,}", " ", s).strip()


def extract_text(path) -> str:
    """Flatten a .docx into plain text — paragraphs + tables (two columns kept as 'left  ||  right'),
    capturing content-control / form-field values and dropping empty placeholders. Capped to fit 8K."""
    import docx
    from docx.oxml.ns import qn
    doc = docx.Document(str(path))
    P, TBL, TR, TC, SDT, SDTC = (qn("w:p"), qn("w:tbl"), qn("w:tr"), qn("w:tc"),
                                 qn("w:sdt"), qn("w:sdtContent"))
    out: list[str] = []

    def walk(parent):
        for child in parent.iterchildren():
            if child.tag == P:                               # paragraph (inline content controls captured)
                t = _strip_ph(_el_text(child))
                if t:
                    out.append(t)
            elif child.tag == TBL:                           # table → rows; keep columns as 'left || right'
                out.append("[TABLE]")
                # iter(TR): catches rows wrapped in repeating-section content controls (w:sdt) too
                for tr in child.iter(TR):
                    # iter(TC): a value cell is often wrapped in a cell-level content control
                    # (w:tr > w:sdt > w:sdtContent > w:tc), which findall(direct children) misses.
                    cells = [_strip_ph(_el_text(tc).replace("\n", " / ")) for tc in tr.iter(TC)]
                    if any(cells):
                        out.append("  ||  ".join(cells))
            elif child.tag == SDT:                           # block-level content control → recurse
                content = child.find(SDTC)
                if content is not None:
                    walk(content)

    walk(doc.element.body)
    text = "\n".join(out).strip()
    if len(text) > _CAP:
        text = text[:_CAP] + "\n…(document truncated to fit the model context)…"
    return text


def _prompt(text: str) -> str:
    cats = ", ".join(C.NET_CATEGORIES)
    return (
        "You convert a customer's network / technical-discovery intake (extracted from a Word document) "
        "into a STRUCTURED network topology. Map what you reasonably can and OMIT anything that doesn't "
        "fit — do not invent devices.\n\n"
        "Return ONLY this JSON (no prose, no code fences):\n"
        '{"sites":[{"label":"<site name>","site_type":"dc"|"branch",'
        '"categories":[{"category":"<one of the allowed categories>","qty_model":"<qty x model>",'
        '"connected_to":"<other categories in THIS site it links to>","notes":"<short note or empty>"}]}]}\n\n'
        f"ALLOWED categories (use the closest match; skip anything that fits none): {cats}\n\n"
        "Rules:\n"
        "- One entry in \"sites\" per physical site (Primary/Core/DC → site_type \"dc\"; "
        "Secondary/DR is also \"dc\"; Remote/Branch → \"branch\").\n"
        "- Put quantities and model names in qty_model (e.g. \"2x Palo Alto PA-850 (HA)\").\n"
        "- IMPORTANT — connected_to drives the arrows: it MUST be a COMMA-separated list of the OTHER "
        "category NAMES in THIS SAME site that this device connects to, using the EXACT allowed category "
        "names (e.g. \"Core Switch, Firewalls\"). Do NOT put model numbers, vendors, ISPs, or prose there "
        "— map the device a thing connects to back to its category (e.g. 'Cisco Nexus 93180' → "
        "\"Core Switch\"). Leave empty if it connects to nothing in this site. Put model/uplink detail in notes.\n"
        "- Group branch locations that share the same infrastructure pattern into one branch site if the "
        "doc says so.\n"
        "- If you can't determine a topology, return {\"sites\":[]}.\n\n"
        f"=== INTAKE DOCUMENT ===\n{text}\n\n=== END ===\nJSON:")


def _coerce(d) -> dict:
    """Coerce the model output into a {'sites':[...]} dict the network writer accepts."""
    if not isinstance(d, dict):
        return {"sites": []}
    sites = d.get("sites")
    if not isinstance(sites, list):
        return {"sites": []}
    valid = {c.lower(): c for c in C.NET_CATEGORIES}
    out_sites = []
    for s in sites:
        if not isinstance(s, dict):
            continue
        cats = []
        for c in (s.get("categories") or []):
            if not isinstance(c, dict):
                continue
            name = (c.get("category") or "").strip()
            canon = valid.get(name.lower(), name)        # snap to a known category name when possible
            if not canon:
                continue
            cats.append({
                "category": canon,
                "qty_model": (c.get("qty_model") or "").strip(),
                "connected_to": (c.get("connected_to") or "").strip(),
                "notes": (c.get("notes") or "").strip(),
            })
        st = (s.get("site_type") or "branch").strip().lower()
        out_sites.append({"label": (s.get("label") or "Site").strip(),
                          "site_type": "dc" if st == "dc" else "branch",
                          "categories": cats})
    # Resolve connected_to → the real category names IN THE SAME SITE (comma-joined) so the network
    # generator (which splits on commas + matches category names) actually draws the arrows. This
    # normalizes the model's free-text / semicolon output into edges.
    for s in out_sites:
        names = [c["category"] for c in s["categories"]]
        for c in s["categories"]:
            c["connected_to"] = _resolve_connections(c["connected_to"], names, c["category"])
    return {"sites": out_sites}


def _resolve_connections(raw: str, site_categories: list, self_name: str) -> str:
    """Map a free-text connected_to (commas/semicolons/prose, device or category names) to a comma-
    separated list of the actual category names present in the same site — what the generator needs
    to draw edges. Matches a category if its name appears in (or equals) a connected_to token."""
    import re
    tokens = [t.strip().lower() for t in re.split(r"[,;/\n]+", raw or "") if t.strip()]
    if not tokens:
        return ""
    hits = []
    for cat in site_categories:
        if cat == self_name:
            continue                                     # no self-edges
        cl = cat.lower()
        for tok in tokens:
            if cl in tok or tok in cl:                   # partial match either direction (like the generator)
                hits.append(cat)
                break
    return ", ".join(dict.fromkeys(hits))                # dedupe, preserve order


def parse_to_network(text: str, on_log=None, should_cancel=None) -> dict:
    """Nemotron maps the intake text → {'sites':[…]}. Fail-soft to {'sites':[]}."""
    if not (text or "").strip():
        return {"sites": []}
    if on_log:
        on_log("🧠 Nemotron is reading the Word document and mapping it to a network intake…")
    try:
        # Generous output budget: Nemotron emits a long <think> block before the JSON; too small a cap
        # truncates the JSON mid-object. Input is capped (_CAP) so input + this fits the 8K window.
        raw = nemotron.complete(_prompt(text), on_log=on_log, max_tokens=6000, should_cancel=should_cancel)
        return _coerce(extract_json(raw))
    except nemotron.Cancelled:
        raise
    except Exception as e:  # noqa: BLE001
        if on_log:
            on_log(f"⚠ Could not parse the document ({str(e)[:120]}).")
        return {"sites": []}
