"""Build draw.io (mxGraphModel) XML from structured briefing data.

Ported/simplified from C:\\ATPtool\\...\\drawio_generator.py — same XML shape
(mxfile > diagram > mxGraphModel > mxCell) that opens natively in diagrams.net.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

# likelihood / status -> (fill, stroke)
_LIKELIHOOD = {
    "high": ("#10311f", "#39d353"),
    "medium": ("#3a341b", "#f0b429"),
    "low": ("#3a1b1b", "#f85149"),
}
_DEFAULT = ("#21262d", "#8b949e")


def _cell(cid: int, value: str, x: int, y: int, w: int, h: int, style: str) -> str:
    return (
        f'<mxCell id="{cid}" value="{escape(str(value))}" style="{style}" vertex="1" '
        f'parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )


def _edge(cid: int, src: int, tgt: int, label: str = "") -> str:
    return (
        f'<mxCell id="{cid}" value="{escape(label)}" style="edgeStyle=orthogonalEdgeStyle;'
        f'rounded=1;html=1;strokeColor=#8b949e;endArrow=block;" edge="1" parent="1" '
        f'source="{src}" target="{tgt}"><mxGeometry relative="1" as="geometry"/></mxCell>'
    )


def _wrap(name: str, cells: list[str]) -> str:
    inner = "".join(cells)
    return (
        '<mxfile host="app.diagrams.net">'
        f'<diagram name="{escape(name)}">'
        '<mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" '
        'connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1500" '
        'pageHeight="1000" math="0" shadow="0"><root>'
        '<mxCell id="0"/><mxCell id="1" parent="0"/>'
        f"{inner}</root></mxGraphModel></diagram></mxfile>"
    )


def decision_tree(dt: dict) -> str:
    """Build a decision-tree diagram from {central_question, branches:[...]}."""
    cells: list[str] = []
    cid = 2
    question = dt.get("central_question") or "Strategic decision"
    center = cid
    cells.append(_cell(
        cid, "❓ " + question, 560, 40, 420, 80,
        "rounded=1;html=1;whiteSpace=wrap;fillColor=#1f6feb;strokeColor=#1158c7;"
        "fontColor=#ffffff;fontStyle=1;fontSize=13;"))
    cid += 1

    branches = dt.get("branches") or []
    n = max(len(branches), 1)
    span = 1440
    bw = min(280, span // n - 20)
    for i, b in enumerate(branches):
        x = 40 + i * (span // n)
        like = str(b.get("likelihood") or "medium").lower()
        fill, stroke = _LIKELIHOOD.get(like, _DEFAULT)
        path = b.get("path") or f"Option {i + 1}"
        pos = b.get("our_position") or ""
        val = f"{path}\n[{like}]\n{pos}".strip()
        bnode = cid
        cells.append(_cell(cid, val, x, 280, bw, 120,
                           f"rounded=1;html=1;whiteSpace=wrap;fillColor={fill};"
                           f"strokeColor={stroke};fontColor=#e6edf3;fontSize=11;"))
        cells.append(_edge(900 + i, center, bnode))
        cid += 1

        leads = b.get("leads_to")
        leads_txt = ", ".join(leads) if isinstance(leads, list) else str(leads or "")
        if leads_txt:
            cells.append(_cell(cid, "→ " + leads_txt, x, 440, bw, 90,
                               "rounded=1;html=1;whiteSpace=wrap;fillColor=#161b22;"
                               "strokeColor=#30363d;fontColor=#8b949e;fontSize=10;"))
            cells.append(_edge(1900 + i, bnode, cid))
            cid += 1
    return _wrap("Decision Tree", cells)


_STATUS = {
    "active": ("#10311f", "#39d353"), "pilot": ("#3a341b", "#f0b429"),
    "planned": ("#1b2f3a", "#56d4dd"), "evaluation": ("#2a1b3a", "#a371f7"),
    "legacy": ("#3a1b1b", "#f85149"),
}


def topology(techs: list[dict], account: str) -> str:
    """Group technologies by category into columns, status-colored."""
    cats: dict[str, list[dict]] = {}
    for t in techs or []:
        cats.setdefault(str(t.get("category") or "Other").title(), []).append(t)
    cells = [_cell(2, f"{account} — Technology Topology", 60, 20, 1080, 50,
                   "rounded=1;html=1;fillColor=#1a1a2e;strokeColor=#333366;"
                   "fontColor=#e0e0ff;fontStyle=1;fontSize=14;")]
    cid, colw = 3, 340
    for ci, (cat, items) in enumerate(cats.items()):
        x = 60 + ci * colw
        cells.append(_cell(cid, cat, x, 100, colw - 30, 44,
                           "rounded=1;html=1;fillColor=#667eea;strokeColor=#5a67d8;"
                           "fontColor=#ffffff;fontStyle=1;fontSize=12;"))
        cid += 1
        for ri, t in enumerate(items):
            st = str(t.get("status") or "").lower()
            fill, stroke = _STATUS.get(st, _DEFAULT)
            label = f"{t.get('vendor', '')} {t.get('product', '')}".strip() + (f"\n[{st}]" if st else "")
            cells.append(_cell(cid, label, x + 10, 168 + ri * 86, colw - 50, 62,
                               f"rounded=1;html=1;whiteSpace=wrap;fillColor={fill};"
                               f"strokeColor={stroke};fontColor=#e6edf3;fontSize=11;"))
            cid += 1
    return _wrap("Topology", cells)


def initiatives_map(initiatives: list[dict], account: str) -> str:
    """A simple column of current initiatives with status coloring."""
    status_color = {
        "active": ("#10311f", "#39d353"), "planning": ("#1b2f3a", "#56d4dd"),
        "stalled": ("#3a341b", "#f0b429"), "blocked": ("#3a1b1b", "#f85149"),
        "completed": ("#21262d", "#8b949e"),
    }
    cells = [_cell(2, f"{account} — Current Initiatives", 60, 30, 520, 50,
                   "rounded=1;html=1;fillColor=#1a1a2e;strokeColor=#333366;"
                   "fontColor=#e0e0ff;fontStyle=1;fontSize=14;")]
    cid = 3
    for i, it in enumerate(initiatives or []):
        st = str(it.get("status") or "").lower()
        fill, stroke = status_color.get(st, _DEFAULT)
        label = f"{it.get('project', 'Initiative')}\n[{st or 'n/a'}]\n{it.get('next_milestone', '')}"
        cells.append(_cell(cid, label, 90, 110 + i * 110, 460, 90,
                           f"rounded=1;html=1;whiteSpace=wrap;fillColor={fill};"
                           f"strokeColor={stroke};fontColor=#e6edf3;fontSize=11;"))
        cid += 1
    return _wrap("Initiatives", cells)
