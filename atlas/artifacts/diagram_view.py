"""Write a self-contained HTML that renders a .drawio diagram via the diagrams.net viewer."""
from __future__ import annotations

import html
import json
from pathlib import Path


def write_viewer(drawio_xml: str, out_html: Path, title: str = "Diagram") -> Path:
    cfg = {"highlight": "#39d353", "nav": True, "resize": True, "toolbar": "zoom layers",
           "xml": drawio_xml}
    data_attr = html.escape(json.dumps(cfg), quote=True)
    page = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>html,body{{margin:0;height:100%;background:#0d1117;font-family:Segoe UI,Arial}}
h3{{color:#e6edf3;padding:10px 16px;margin:0}}
.mxgraph{{background:#0d1117}}</style></head>
<body><h3>{html.escape(title)}</h3>
<div class="mxgraph" style="max-width:100%;border:1px solid #30363d;" data-mxgraph="{data_attr}"></div>
<script src="https://viewer.diagrams.net/js/viewer-static.min.js"></script>
</body></html>"""
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(page, encoding="utf-8")
    return out_html
