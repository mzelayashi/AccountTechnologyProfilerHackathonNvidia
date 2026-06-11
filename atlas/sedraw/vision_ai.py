"""Free-form text → structured vision-board data, via the local Nemotron model.

Ported from the SEDraw CLI's ai_assistant (prompt + parse + validate), driving
atlas.engine.nemotron instead of the old Mindspark client. Takes two free-form text blocks
(current state, future state) and returns:
    {"current_state": {"systems":[...], "data_flows":[...]}, "future_state": {...}}
(only the states that were provided). The output round-trips through ExcelReader.read_vision_board.
"""
from __future__ import annotations

import json
import re

from atlas.sedraw.excel_reader import ExcelReader

SYSTEM_HEADERS = ["system_name", "vendor", "role", "status", "tier",
                  "color_hint", "notes", "description", "use_cases", "pain_points"]
FLOW_HEADERS = ["source", "target", "label", "flow_type", "line_style"]

VALID_STATUSES = sorted(ExcelReader.VALID_STATUSES)
VALID_TIERS = sorted(ExcelReader.VALID_TIERS)
VALID_FLOW_TYPES = sorted(ExcelReader.VALID_FLOW_TYPES)
VALID_LINE_STYLES = sorted(ExcelReader.VALID_LINE_STYLES)

TIER_RULES = """Tier assignment rules:
- source: Systems that originate data (POS, CRM, ERP, SaaS apps, databases, IoT)
- integration: Middleware, iPaaS, ETL tools, message brokers (Boomi, MuleSoft, Kafka, Informatica)
- hub: Central data platforms, data lakes, data warehouses, lakehouses (Snowflake, Databricks, Azure Data Lake)
- consumer: BI tools, dashboards, reporting, visualization (Power BI, Tableau, Domo, Looker)
- ai: AI/ML platforms, predictive analytics, copilots, GenAI services (Azure AI, SageMaker, Vertex AI)"""


def _build_prompt(customer_name: str, description: str) -> str:
    has_current = "CURRENT STATE" in description.upper()
    has_future = "FUTURE STATE" in description.upper()
    if not has_current and not has_future:
        state_instruction = ('The user did not specify sections. If the description covers current '
                             'technology return "current_state"; if future/planned return '
                             '"future_state"; if both, return both.')
    else:
        states = []
        if has_current:
            states.append('"current_state"')
        if has_future:
            states.append('"future_state"')
        state_instruction = f"Return these state keys: {' and '.join(states)}"

    return f"""You are a Solutions Engineering data architect. Convert a free-form description of a customer's technology landscape into structured JSON used to generate architecture diagrams.

CUSTOMER: {customer_name}

OUTPUT FORMAT:
Return ONLY a valid JSON object (no markdown, no explanation, no code fences) with this structure:
{{
  "current_state": {{ "systems": [...], "data_flows": [...] }},
  "future_state": {{ "systems": [...], "data_flows": [...] }}
}}

{state_instruction}

SYSTEMS SCHEMA (all 10 fields required per system):
- system_name (string): Technology/platform name
- vendor (string): Company/vendor name
- role (string): Brief role (e.g., "Cloud Data Warehouse", "iPaaS / Integration")
- status (string): One of: {", ".join(VALID_STATUSES)}
  ("current" = in use; "retiring" = being phased out; "new" = being implemented; "planned" = roadmap/evaluation)
- tier (string): One of: {", ".join(VALID_TIERS)}
{TIER_RULES}
- color_hint (string): Optional hex color or empty string
- notes (string): Brief note (e.g., "Replaces Domo", "Retained") or empty string
- description (string): 1-2 sentence description of what this system does here
- use_cases (string): Key capabilities, pipe-separated (e.g., "ETL | Cleansing | Transform")
- pain_points (string): Known issues, pipe-separated, or empty string

DATA FLOWS SCHEMA (all 5 fields required per flow):
- source (string): Must EXACTLY match a system_name
- target (string): Must EXACTLY match a system_name
- label (string): Short description (e.g., "data feed", "API sync")
- flow_type (string): One of: {", ".join(VALID_FLOW_TYPES)}
- line_style (string): One of: {", ".join(VALID_LINE_STYLES)} (solid=active, dashed=planned, dotted=integration)

RULES:
1. Return ONLY valid JSON. No markdown fences, no text before/after.
2. Flow source/target must EXACTLY match a system_name.
3. Every system has all 10 fields (empty string "" where unknown).
4. Status by context: replaced = "retiring", new builds = "new", evaluations = "planned", else "current".
5. Create logical data flows between systems based on the architecture described.

CUSTOMER DESCRIPTION:
{description}

Generate the JSON now:"""


def _parse_ai_response(response: str) -> dict | None:
    if not response or not response.strip():
        return None
    text = response.strip()
    text = re.sub(r'^```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?```\s*$', '', text).strip()
    a, b = text.find('{'), text.rfind('}')
    if a == -1 or b == -1 or b <= a:
        return None
    js = re.sub(r',(\s*[}\]])', r'\1', text[a:b + 1])   # drop trailing commas
    try:
        data = json.loads(js)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    valid = {'current_state', 'future_state'}
    if not (set(data) & valid):
        return None
    for k in list(data):
        if k not in valid:
            del data[k]
        else:
            data[k].setdefault('systems', [])
            data[k].setdefault('data_flows', [])
    return data


def _norm_hex(c: str) -> str:
    """Return a normalized #RRGGBB color or '' — guards the diagram generator from bad LLM colors."""
    s = (c or '').strip().lstrip('#')
    if re.fullmatch(r'[0-9a-fA-F]{6}', s):
        return '#' + s.lower()
    if re.fullmatch(r'[0-9a-fA-F]{3}', s):
        return '#' + ''.join(ch * 2 for ch in s).lower()
    return ''


def _fix_system(s: dict) -> dict:
    out = {h: str(s.get(h, '') or '').strip() for h in SYSTEM_HEADERS}
    st = out['status'].lower().replace(' ', '_')
    out['status'] = st if st in ExcelReader.VALID_STATUSES else 'current'
    ti = out['tier'].lower().replace(' ', '_')
    out['tier'] = ti if ti in ExcelReader.VALID_TIERS else 'source'
    out['color_hint'] = _norm_hex(out['color_hint'])
    return out


def _match(name, names, names_lower):
    if name in names:
        return name
    return names_lower.get(name.lower())


def _fix_flow(f: dict, names, names_lower) -> dict | None:
    src = _match(str(f.get('source', '')).strip(), names, names_lower)
    tgt = _match(str(f.get('target', '')).strip(), names, names_lower)
    if not src or not tgt:
        return None
    ft = str(f.get('flow_type', 'data_feed')).strip().lower().replace(' ', '_')
    ls = str(f.get('line_style', 'solid')).strip().lower()
    return {"source": src, "target": tgt, "label": str(f.get('label', 'data flow')).strip(),
            "flow_type": ft if ft in ExcelReader.VALID_FLOW_TYPES else 'data_feed',
            "line_style": ls if ls in ExcelReader.VALID_LINE_STYLES else 'solid'}


def _validate_and_fix(data: dict) -> dict:
    for key in list(data):
        state = data[key]
        systems = [_fix_system(s) for s in state.get('systems', []) if isinstance(s, dict)]
        systems = [s for s in systems if s.get('system_name')]
        names = {s['system_name'] for s in systems}
        names_lower = {n.lower(): n for n in names}
        flows = []
        for f in state.get('data_flows', []):
            if isinstance(f, dict):
                fx = _fix_flow(f, names, names_lower)
                if fx:
                    flows.append(fx)
        data[key] = {"systems": systems, "data_flows": flows}
    return data


def _build_single_prompt(customer: str, state_label: str, text: str) -> str:
    """Prompt for ONE state — output is a plain {"systems":[...], "data_flows":[...]} object.
    Smaller output than asking for both states at once → reliable + fast at an 8192 window."""
    return f"""You are a Solutions Engineering data architect. Convert a free-form description of a customer's technology landscape into structured JSON for an architecture diagram.

CUSTOMER: {customer}
This describes the **{state_label}** of the architecture.

OUTPUT FORMAT — return ONLY a valid JSON object (no markdown, no code fences, no explanation):
{{ "systems": [...], "data_flows": [...] }}

SYSTEMS SCHEMA (all 10 fields per system):
- system_name, vendor, role
- status: one of {", ".join(VALID_STATUSES)} (current=in use, retiring=phasing out, new=being built, planned=roadmap)
- tier: one of {", ".join(VALID_TIERS)}
{TIER_RULES}
- color_hint (hex or ""), notes (or ""), description (1-2 sentences),
- use_cases (pipe-separated or ""), pain_points (pipe-separated or "")

DATA FLOWS SCHEMA (all 5 fields per flow):
- source, target (must EXACTLY match a system_name)
- label, flow_type (one of {", ".join(VALID_FLOW_TYPES)}), line_style (one of {", ".join(VALID_LINE_STYLES)})

RULES: only valid JSON; flow source/target must match a system_name; every system has all 10 fields ("" where unknown); create logical flows between systems.

DESCRIPTION ({state_label}):
{text}

Generate the JSON now:"""


def _parse_single(response: str) -> dict | None:
    if not response or not response.strip():
        return None
    text = re.sub(r'\n?```\s*$', '', re.sub(r'^```(?:json)?\s*\n?', '', response.strip())).strip()
    a, b = text.find('{'), text.rfind('}')
    if a == -1 or b == -1 or b <= a:
        return None
    try:
        d = json.loads(re.sub(r',(\s*[}\]])', r'\1', text[a:b + 1]))
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict):
        return None
    return {"systems": d.get("systems", []) or [], "data_flows": d.get("data_flows", []) or []}


def generate_states(current_text: str = "", future_text: str = "", customer: str = "",
                    on_log=None) -> dict:
    """Turn the two free-form text blocks into validated {current_state, future_state} data.
    Runs the two states as SEPARATE concurrent Nemotron calls (smaller output each → reliable + fast)."""
    import concurrent.futures as cf
    from atlas.engine import nemotron
    jobs = []
    if (current_text or "").strip():
        jobs.append(("current_state", "current state", current_text.strip()))
    if (future_text or "").strip():
        jobs.append(("future_state", "future state", future_text.strip()))
    if not jobs:
        return {}

    def _run(job):
        key, label, text = job
        prompt = _build_single_prompt(customer or "the customer", label, text)
        for _ in range(2):
            if on_log:
                on_log(f"Nemotron structuring the {label}…")
            d = _parse_single(nemotron.complete(prompt, on_log=on_log))
            if d:
                return key, d
            prompt += "\n\nReturn ONLY the JSON object, nothing else."
        return key, {"systems": [], "data_flows": []}

    out = {}
    with cf.ThreadPoolExecutor(max_workers=2) as ex:
        for key, data in ex.map(_run, jobs):
            out[key] = data
    return _validate_and_fix(out)
