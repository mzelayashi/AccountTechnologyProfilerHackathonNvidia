"""Render a customer's technology profile as the ATP topology diagram — a carbon-copy of the
SHI Account Technology Profiler's topology tab (10 glowing category columns, oval status-colored
tech boxes), self-contained HTML so it loads inside ATLAS. Click a box to see its specs.
"""
from __future__ import annotations

import html
import json

from atlas.atp import data_library
from atlas.store import customers

_COLUMNS = ["Cloud", "Servers", "Block/File", "Networking", "End User",
            "UCC", "IoT/Physical", "Software", "Security", "Services"]

# Keyword catalog — verbatim from the original ATP _organize_tech_profile().
_KW = {
    "cloud": ["aws", "azure", "gcp", "google cloud", "oracle cloud", "cloud", "saas"],
    "server": ["vmware", "vsphere", "esxi", "hyper-v", "nutanix", "citrix", "dell compute", "hpe", "server", "vm", "hypervisor"],
    "storage": ["netapp", "pure storage", "dell emc", "veeam", "commvault", "rubrik", "cohesity", "backup", "storage", "san", "nas"],
    "network": ["cisco catalyst", "cisco switch", "meraki mx", "meraki ms", "juniper", "arista", "palo alto", "fortinet", "fortigate", "firewall", "switch", "router", "sd-wan", "wireless", "wifi", "aruba"],
    "endpoint": ["latitude", "optiplex", "precision", "elitebook", "probook", "elitedesk", "prodesk", "thinkpad", "thinkcentre", "surface", "macbook", "imac", "chromebook", "thin client", "laptop", "desktop", "workstation", "iphone", "ipad", "android", "mobile device"],
    "ucc": ["zoom", "teams room", "webex", "polycom", "poly", "lifesize", "video conferencing", "voip", "phone system", "pbx", "cucm", "ringcentral", "8x8", "avaya", "mitel", "yealink", "teams phone", "webex calling", "slack", "collaboration", "conference room"],
    "iot": ["camera", "cctv", "surveillance", "verkada", "axis", "hikvision", "nvr", "dvr", "access control", "badge", "hid", "lenel", "genetec", "alarm", "sensor", "hvac", "building automation", "thermostat", "printer", "mfp", "copier", "xerox", "ricoh", "canon printer"],
    "mdm": ["intune", "jamf", "workspace one", "airwatch", "mobileiron", "kandji", "mdm", "uem"],
    "software": ["microsoft", "office", "m365", "sql", "oracle", "sap", "servicenow", "database", "erp", "crm", "adobe"],
    "security": ["crowdstrike", "sentinelone", "defender", "edr", "xdr", "siem", "splunk", "mfa", "duo", "okta", "cyberark", "knowbe4", "sophos", "antivirus"],
}


def _column_for(vendor: str, product: str, category: str) -> str:
    c = f"{(vendor or '').lower()} {(product or '').lower()}"
    if any(k in c for k in _KW["ucc"]):
        return "UCC"
    if any(k in c for k in _KW["iot"]):
        return "IoT/Physical"
    if any(k in c for k in _KW["mdm"]) or any(k in c for k in _KW["endpoint"]):
        return "End User"
    if any(k in c for k in _KW["cloud"]):
        return "Cloud"
    if any(k in c for k in _KW["server"]):
        return "Servers"
    if any(k in c for k in _KW["storage"]):
        return "Block/File"
    if any(k in c for k in _KW["network"]):
        return "Networking"
    if any(k in c for k in _KW["security"]):
        return "Security"
    if any(k in c for k in _KW["software"]):
        return "Software"
    return {"datacenter": "Servers", "networking": "Networking",
            "security": "Security", "edge_iot": "End User"}.get((category or "").lower(), "Software")


def _organize(entries: list[dict]) -> dict:
    cols = {c: [] for c in _COLUMNS}
    seen = {c: set() for c in _COLUMNS}
    for e in entries:
        vendor = (e.get("vendor") or "").strip()
        if not vendor:
            continue
        product = (e.get("product") or "").strip()
        name = f"{vendor} - {product}" if product else vendor
        col = _column_for(vendor, product, e.get("category", ""))
        if name in seen[col]:
            continue
        seen[col].add(name)
        cols[col].append({
            "name": name,
            "status": (e.get("deployment_status") or "unknown").lower(),
            "specs": _spec_lines(e),
        })
    return {c: v for c, v in cols.items() if v}


def _spec_lines(e: dict) -> str:
    lines = []
    # Relevancy first (deterministic, from the trip reports) — the user's key signal.
    mc = e.get("mention_count") or 0
    if mc:
        lines.append(f"Appears in {mc} trip report{'s' if mc != 1 else ''}")
        if (e.get("last_seen_report") or "").strip():
            lines.append(f"Last seen: {e['last_seen_report'].strip()}")
        elif (e.get("last_seen") or "").strip():
            lines.append(f"Last seen: {e['last_seen'].strip()}")
    for label, key in (("Model", "model_number"), ("Version", "version"),
                       ("Status", "deployment_status"), ("Deployment %", "deployment_percentage"),
                       ("Satisfaction", "satisfaction_level")):
        v = (e.get(key) or "").strip() if isinstance(e.get(key), str) else e.get(key)
        if v:
            lines.append(f"{label}: {v}")
    specs = e.get("specifications") or {}
    if isinstance(specs, dict):
        for k, v in specs.items():
            if v:
                lines.append(f"{k}: {v}")
    if (e.get("notes") or "").strip():
        lines.append(f"Notes: {e['notes'].strip()}")
    return "\n".join(lines) or "No additional specs recorded."


def _columns_html(cols: dict) -> str:
    out = []
    for category, techs in cols.items():
        boxes = []
        for t in techs[:8]:
            specs = html.escape(t["specs"], quote=True)
            boxes.append(f'<div class="tech-box status-{html.escape(t["status"])}" '
                         f'data-name="{html.escape(t["name"], quote=True)}" '
                         f'data-specs="{specs}" onclick="showSpecs(this)">{html.escape(t["name"])}</div>')
        while len(boxes) < 3:
            boxes.append('<div class="tech-box empty"></div>')
        out.append(f'<div class="tech-column"><div class="tech-header">{html.escape(category)}</div>'
                   f'<div class="tech-items">{"".join(boxes)}</div></div>')
    return "".join(out)


def render(customer_name: str, entries: list[dict]) -> str:
    cols = _organize(entries)
    columns_html = _columns_html(cols)
    total = sum(len(v) for v in cols.values())
    summary = f"<span>{total} Technologies</span>" if total else "<span>No technologies yet — add some in the editor</span>"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>{html.escape(customer_name)} — Technology Topology</title>
<style>{_CSS}</style></head>
<body>
<div class="container tech-profile-container">
  <div class="tech-profile-header">
    <h1 class="tech-profile-title">{html.escape(customer_name)} — Technology Topology</h1>
    <div class="tech-profile-summary">{summary}</div>
  </div>
  <div class="status-legend">
    <span class="legend-title">Deployment Status:</span>
    <span class="legend-item"><span class="legend-dot status-active"></span>Active/Deployed</span>
    <span class="legend-item"><span class="legend-dot status-planned"></span>Planned</span>
    <span class="legend-item"><span class="legend-dot status-pilot"></span>Pilot/POC</span>
    <span class="legend-item"><span class="legend-dot status-legacy"></span>Legacy</span>
    <span class="legend-item"><span class="legend-dot status-unknown"></span>Unknown</span>
  </div>
  <div class="tech-profile-grid">{columns_html}</div>
</div>
<div id="specpanel" class="specpanel"><div class="specname" id="specname"></div>
  <pre id="specbody"></pre><button onclick="document.getElementById('specpanel').classList.remove('show')">close</button></div>
<script>
function showSpecs(el){{
  document.getElementById('specname').textContent=el.getAttribute('data-name');
  document.getElementById('specbody').textContent=el.getAttribute('data-specs');
  document.getElementById('specpanel').classList.add('show');
}}
</script>
</body></html>"""


def write(customer_name: str) -> str:
    """Render from the saved data_library and write topology.html into the customer folder."""
    entries = data_library.load(customer_name)
    html_str = render(customer_name, entries)
    p = customers.customer_dir(customer_name) / "account_technology_profile" / "topology.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html_str, encoding="utf-8")
    return p.as_uri()


# ---- the topology CSS, ported faithfully from html_generator_v2._get_tech_profile_css() ----
_CSS = """
* { box-sizing: border-box; }
body { margin:0; background: linear-gradient(135deg, #0a0a1a 0%, #1a1a2e 50%, #0f0f23 100%);
  min-height: 100vh; font-family:'Segoe UI',Arial,sans-serif; color:#fff; }
.tech-profile-container { max-width: 1500px; margin: 0 auto; padding: 30px; position: relative; }
.tech-profile-header { text-align:center; margin-bottom:34px; padding:34px;
  background: linear-gradient(135deg, rgba(10,10,30,0.95) 0%, rgba(20,20,50,0.95) 100%);
  border-radius:25px; border:2px solid rgba(0,255,255,0.3);
  box-shadow:0 0 30px rgba(0,255,255,0.2), inset 0 0 60px rgba(0,255,255,0.05);
  position:relative; overflow:hidden; }
.tech-profile-header::before { content:''; position:absolute; top:-50%; left:-50%; width:200%; height:200%;
  background: conic-gradient(from 0deg, transparent, rgba(0,255,255,0.1), transparent 30%); animation: rotate 10s linear infinite; }
@keyframes rotate { 100% { transform: rotate(360deg); } }
.tech-profile-title { font-size:2.2em; margin:0 0 16px 0; font-weight:700; color:#00ffff;
  text-shadow:0 0 10px rgba(0,255,255,0.8),0 0 20px rgba(0,255,255,0.5); letter-spacing:2px; position:relative; z-index:1; }
.tech-profile-summary { font-size:1.1em; color:rgba(255,255,255,0.9); position:relative; z-index:1; }
.tech-profile-summary span { display:inline-block; margin:0 12px; padding:6px 18px;
  background:rgba(0,255,255,0.1); border:1px solid rgba(0,255,255,0.3); border-radius:20px; color:#00ffff; }
.status-legend { display:flex; justify-content:center; gap:24px; margin-bottom:24px; flex-wrap:wrap; }
.legend-title { color:rgba(255,255,255,0.6); font-size:0.85em; }
.legend-item { display:flex; align-items:center; gap:6px; color:rgba(255,255,255,0.8); font-size:0.85em; }
.legend-dot { width:12px; height:12px; border-radius:50%; display:inline-block; }
.legend-dot.status-active { background:#00e676; box-shadow:0 0 8px #00e676; }
.legend-dot.status-planned { background:#2196f3; box-shadow:0 0 8px #2196f3; }
.legend-dot.status-pilot { background:#ffc107; box-shadow:0 0 8px #ffc107; }
.legend-dot.status-legacy { background:#ff5722; box-shadow:0 0 8px #ff5722; }
.legend-dot.status-unknown { background:#9e9e9e; box-shadow:0 0 8px #9e9e9e; }
.tech-profile-grid { display:flex; flex-wrap:wrap; gap:50px; justify-content:center; padding:40px 0; position:relative; }
.tech-profile-grid::before { content:''; position:absolute; top:40%; left:5%; right:5%; height:3px;
  background:linear-gradient(90deg,transparent,rgba(0,255,255,0.6) 15%,rgba(0,255,255,0.8) 50%,rgba(0,255,255,0.6) 85%,transparent);
  box-shadow:0 0 15px rgba(0,255,255,0.8); z-index:0; }
.tech-column { flex:0 0 auto; min-width:200px; max-width:240px; position:relative; z-index:1; }
.tech-column::before { content:''; position:absolute; left:50%; top:70px; bottom:30px; width:2px;
  background:linear-gradient(180deg,transparent,rgba(0,255,255,0.3) 10%,rgba(0,255,255,0.5) 50%,rgba(0,255,255,0.3) 90%,transparent); z-index:0; }
.tech-column:nth-child(8n+1) .tech-header { background:linear-gradient(180deg,#00bcd4,#0097a7); }
.tech-column:nth-child(8n+1) .tech-items { border-color:#00bcd4; box-shadow:0 0 20px rgba(0,188,212,0.4); }
.tech-column:nth-child(8n+2) .tech-header { background:linear-gradient(180deg,#7c4dff,#651fff); }
.tech-column:nth-child(8n+2) .tech-items { border-color:#7c4dff; box-shadow:0 0 20px rgba(124,77,255,0.4); }
.tech-column:nth-child(8n+3) .tech-header { background:linear-gradient(180deg,#ff4081,#f50057); }
.tech-column:nth-child(8n+3) .tech-items { border-color:#ff4081; box-shadow:0 0 20px rgba(255,64,129,0.4); }
.tech-column:nth-child(8n+4) .tech-header { background:linear-gradient(180deg,#00e676,#00c853); }
.tech-column:nth-child(8n+4) .tech-items { border-color:#00e676; box-shadow:0 0 20px rgba(0,230,118,0.4); }
.tech-column:nth-child(8n+5) .tech-header { background:linear-gradient(180deg,#ffab00,#ff8f00); }
.tech-column:nth-child(8n+5) .tech-items { border-color:#ffab00; box-shadow:0 0 20px rgba(255,171,0,0.4); }
.tech-column:nth-child(8n+6) .tech-header { background:linear-gradient(180deg,#18ffff,#00e5ff); }
.tech-column:nth-child(8n+6) .tech-items { border-color:#18ffff; box-shadow:0 0 20px rgba(24,255,255,0.4); }
.tech-column:nth-child(8n+7) .tech-header { background:linear-gradient(180deg,#ea80fc,#e040fb); }
.tech-column:nth-child(8n+7) .tech-items { border-color:#ea80fc; box-shadow:0 0 20px rgba(234,128,252,0.4); }
.tech-column:nth-child(8n+8) .tech-header { background:linear-gradient(180deg,#64ffda,#1de9b6); }
.tech-column:nth-child(8n+8) .tech-items { border-color:#64ffda; box-shadow:0 0 20px rgba(100,255,218,0.4); }
.tech-header { color:white; padding:15px 18px; text-align:center; font-weight:700; font-size:0.95em;
  border-radius:25px 25px 0 0; text-shadow:0 2px 4px rgba(0,0,0,0.3); white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; text-transform:uppercase; letter-spacing:1px; }
.tech-items { background:linear-gradient(180deg,rgba(15,15,35,0.95),rgba(10,10,25,0.98)); border:2px solid;
  border-top:none; border-radius:0 0 25px 25px; min-height:220px; backdrop-filter:blur(10px); padding-bottom:8px; }
.tech-box { padding:12px 15px; margin:10px 8px; font-size:0.85em; color:#fff;
  background:linear-gradient(145deg,rgba(40,40,80,0.8),rgba(20,20,50,0.9)); border:1px solid rgba(0,255,255,0.4);
  border-radius:50px; transition:all 0.3s ease; text-align:center; position:relative; cursor:pointer;
  box-shadow:0 4px 15px rgba(0,0,0,0.3),inset 0 1px 0 rgba(255,255,255,0.1),0 0 10px rgba(0,255,255,0.2);
  text-shadow:0 1px 2px rgba(0,0,0,0.5); }
.tech-box::before { content:''; position:absolute; left:-5px; top:50%; transform:translateY(-50%);
  width:8px; height:8px; background:#00ffff; border-radius:50%; box-shadow:0 0 10px #00ffff,0 0 20px #00ffff; }
.tech-box::after { content:''; position:absolute; right:-5px; top:50%; transform:translateY(-50%);
  width:8px; height:8px; background:#00ffff; border-radius:50%; box-shadow:0 0 10px #00ffff,0 0 20px #00ffff; }
.tech-box:hover { background:linear-gradient(145deg,rgba(0,255,255,0.3),rgba(0,150,150,0.4)); border-color:#00ffff;
  transform:scale(1.05) translateY(-2px); box-shadow:0 8px 25px rgba(0,0,0,0.4),0 0 30px rgba(0,255,255,0.5); color:#00ffff; }
.tech-box.empty { min-height:35px; background:rgba(20,20,40,0.5); border:1px dashed rgba(0,255,255,0.2); box-shadow:none; cursor:default; }
.tech-box.empty::before, .tech-box.empty::after { display:none; }
.tech-box.status-active { border-color:rgba(0,230,118,0.6); box-shadow:0 4px 15px rgba(0,0,0,0.3),0 0 15px rgba(0,230,118,0.4); }
.tech-box.status-active::before, .tech-box.status-active::after { background:#00e676; box-shadow:0 0 10px #00e676,0 0 20px #00e676; }
.tech-box.status-planned { border-color:rgba(33,150,243,0.6); box-shadow:0 4px 15px rgba(0,0,0,0.3),0 0 15px rgba(33,150,243,0.4); }
.tech-box.status-planned::before, .tech-box.status-planned::after { background:#2196f3; box-shadow:0 0 10px #2196f3,0 0 20px #2196f3; }
.tech-box.status-pilot, .tech-box.status-evaluation { border-color:rgba(255,193,7,0.6); box-shadow:0 4px 15px rgba(0,0,0,0.3),0 0 15px rgba(255,193,7,0.4); }
.tech-box.status-pilot::before, .tech-box.status-pilot::after, .tech-box.status-evaluation::before, .tech-box.status-evaluation::after { background:#ffc107; box-shadow:0 0 10px #ffc107,0 0 20px #ffc107; }
.tech-box.status-legacy { border-color:rgba(255,87,34,0.6); box-shadow:0 4px 15px rgba(0,0,0,0.3),0 0 15px rgba(255,87,34,0.3); opacity:0.85; }
.tech-box.status-legacy::before, .tech-box.status-legacy::after { background:#ff5722; box-shadow:0 0 10px #ff5722,0 0 20px #ff5722; }
.tech-box.status-unknown { border-color:rgba(158,158,158,0.4); }
.tech-box.status-unknown::before, .tech-box.status-unknown::after { background:#9e9e9e; box-shadow:0 0 8px #9e9e9e; }
.specpanel { position:fixed; right:24px; bottom:24px; max-width:360px; background:rgba(10,12,24,0.97);
  border:1px solid #00ffff66; border-radius:14px; padding:16px 18px; box-shadow:0 0 30px rgba(0,255,255,0.25);
  display:none; z-index:50; }
.specpanel.show { display:block; }
.specname { color:#00ffff; font-weight:700; margin-bottom:8px; }
.specpanel pre { white-space:pre-wrap; color:#cfe; font-size:13px; margin:0 0 10px; font-family:Consolas,monospace; }
.specpanel button { background:#163049; color:#fff; border:1px solid #1f4d77; border-radius:8px; padding:6px 12px; cursor:pointer; }
"""
