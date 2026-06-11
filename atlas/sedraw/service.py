"""Service layer bridging the ATLAS Customer Vault and the SE Draw diagram engine.

Pure and synchronous — no LLM, no Copilot session, no JobManager. Called directly by
atlas/web/api.py. Inputs/outputs live under each customer's vault folder:
  vault/customers/<slug>/{network_input,network_output,vision_input,vision_output}/
Each generate_* writes a .drawio plus a self-contained diagrams.net viewer .html (served
inline in the GUI via GET /vaultfile?p=...).
"""
from __future__ import annotations

import base64
import datetime
from pathlib import Path

import config
from atlas.artifacts import diagram_view
from atlas.sedraw.drawio_generator import VisionBoardGenerator
from atlas.sedraw.excel_reader import ExcelReader
from atlas.sedraw.network_generator import NetworkTopologyGenerator
from atlas.sedraw.network_reader import NetworkReader
from atlas.store import customers, vault

# kind -> (input_subfolder, output_subfolder)
_KIND = {
    "network": ("network_input", "network_output"),
    "vision": ("vision_input", "vision_output"),
}

# Enum option lists for the Vision editor dropdowns.
VISION_STATUSES = sorted(ExcelReader.VALID_STATUSES)            # current, new, planned, retiring
VISION_TIERS = ["source", "integration", "hub", "consumer", "ai"]
VISION_FLOW_TYPES = sorted(ExcelReader.VALID_FLOW_TYPES)
VISION_LINE_STYLES = sorted(ExcelReader.VALID_LINE_STYLES)


def _xlsx(d: Path) -> list[Path]:
    if not d.exists():
        return []
    return sorted(p for p in d.glob("*.xlsx") if not p.name.startswith("~$"))


def _rel_to_vault(p: Path) -> str:
    return str(p.resolve().relative_to(config.VAULT_DIR.resolve())).replace("\\", "/")


def _result(drawio_path: Path, viewer_html: Path, title: str) -> dict:
    return {
        "ok": True,
        "title": title,
        "drawio_uri": drawio_path.as_uri(),
        "drawio_name": drawio_path.name,
        "viewer": _rel_to_vault(viewer_html),   # GET /vaultfile?p=<this>
    }


def list_customers() -> list[dict]:
    """Vault customers annotated with whether they have network/vision input + output."""
    out = customers.list_customers()
    for c in out:
        cdir = config.CUSTOMERS_DIR / c["slug"]
        c["has_network_input"] = bool(_xlsx(cdir / "network_input"))
        c["has_vision_input"] = bool(_xlsx(cdir / "vision_input"))
        c["has_network_output"] = bool(list((cdir / "network_output").glob("*.drawio")))
        c["has_vision_output"] = bool(list((cdir / "vision_output").glob("*.drawio")))
    return out


def inputs(customer: str, kind: str) -> list[dict]:
    """List the input .xlsx files for a customer in the given kind ('network'|'vision')."""
    in_sub, _ = _KIND[kind]
    cdir = customers.customer_dir(customer)        # ensures the subfolders exist
    return [{"name": p.name} for p in _xlsx(cdir / in_sub)]


def save_upload(customer: str, kind: str, filename: str, data_b64: str) -> dict:
    """Decode a base64 (optionally data-URI) payload into the customer's input folder."""
    if kind not in _KIND:
        return {"ok": False, "error": f"unknown kind: {kind}"}
    if not (filename or "").lower().endswith(".xlsx"):
        return {"ok": False, "error": "Please upload an .xlsx file."}
    in_sub, _ = _KIND[kind]
    cdir = customers.customer_dir(customer)
    safe = Path(filename).name                     # strip any path components
    try:
        raw = base64.b64decode((data_b64 or "").split(",")[-1])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"could not decode upload: {e}"}
    (cdir / in_sub / safe).write_bytes(raw)
    return {"ok": True, "name": safe}


def _pick(files: list[Path], filename: str) -> Path:
    return next((f for f in files if f.name == filename), files[0])


def _pick_input(customer: str, kind: str, filename: str) -> "Path | None":
    in_sub, _ = _KIND[kind]
    files = _xlsx(customers.customer_dir(customer) / in_sub)
    if not files:
        return None
    return _pick(files, filename)


def load_network(customer: str, filename: str = "") -> dict:
    """Parse a customer's network input .xlsx into the editable structure for the GUI editor."""
    from atlas.sedraw import constants as C
    from atlas.sedraw.network_reader import NetworkReader
    src = _pick_input(customer, "network", filename)
    if not src:
        return {"ok": False, "error": "No network input .xlsx found for this customer."}
    data = NetworkReader().read_network_topology(src)
    return {"ok": True, "filename": src.name, "data": data,
            "categories": list(C.NET_CATEGORIES),          # the 23 names, for "add category"
            "groups": C.NET_CATEGORY_GROUPS}


def _clean_network(data: dict) -> dict:
    """Validate/normalize the edited structure before writing back to Excel."""
    out_sites = []
    for s in (data or {}).get("sites", []):
        label = (s.get("label") or "").strip()
        cats = []
        for c in s.get("categories", []):
            name = (c.get("category") or "").strip()
            if not name:
                continue
            rating = c.get("rating")
            try:
                rating = int(rating) if str(rating).strip() not in ("", "None") else None
            except (TypeError, ValueError):
                rating = None
            cats.append({
                "category": name,
                "qty_model": (c.get("qty_model") or "").strip(),
                "connected_to": (c.get("connected_to") or "").strip(),
                "end_of_support": (c.get("end_of_support") or "").strip(),
                "rating": rating,
                "status": (c.get("status") or "current").strip().lower(),
                "notes": (c.get("notes") or "").strip(),
            })
        if not label and not cats:
            continue                                       # drop fully-empty sites
        out_sites.append({"label": label or "Site",
                          "site_type": (s.get("site_type") or "branch").strip().lower(),
                          "categories": cats})
    return {"sites": out_sites}


def new_network_template(customer: str) -> dict:
    """A blank, editable network template (one starter site) for the 'Create New' flow."""
    from atlas.sedraw import constants as C
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return {"ok": True, "filename": f"{vault.slug(customer)}_network_{ts}.xlsx", "new": True,
            "data": {"sites": [{"label": "Main Site", "site_type": "dc", "categories": []}]},
            "categories": list(C.NET_CATEGORIES), "groups": C.NET_CATEGORY_GROUPS}


def save_network(customer: str, filename: str = "", data: dict | None = None) -> dict:
    """Write the edited structure to the customer's network_input .xlsx — creating the file when it's
    a new name (Create New) or overwriting it when editing an existing one."""
    from atlas.sedraw.network_writer import write_network_topology
    cleaned = _clean_network(data or {})
    if not cleaned["sites"]:
        return {"ok": False, "error": "Nothing to save — add at least one site with a device."}
    nin = customers.customer_dir(customer) / "network_input"
    nin.mkdir(parents=True, exist_ok=True)
    if filename:
        safe = Path(filename).name
        if not safe.lower().endswith(".xlsx"):
            safe += ".xlsx"
        src = nin / safe
    else:
        src = nin / f"{vault.slug(customer)}_network_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    write_network_topology(cleaned, src)
    n_cats = sum(len(s["categories"]) for s in cleaned["sites"])
    return {"ok": True, "filename": src.name, "sites": len(cleaned["sites"]), "categories": n_cats}


def generate_network(customer: str, filename: str = "") -> dict:
    in_sub, out_sub = _KIND["network"]
    cdir = customers.customer_dir(customer)
    files = _xlsx(cdir / in_sub)
    if not files:
        return {"ok": False, "error": "No network input .xlsx found for this customer."}
    src = _pick(files, filename)
    data = NetworkReader().read_network_topology(src)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    out = cdir / out_sub / f"{vault.slug(customer)}_{src.stem}_{ts}.drawio"
    NetworkTopologyGenerator().generate(customer, data, out)
    title = f"{customer} — Network Topology"
    viewer = diagram_view.write_viewer(out.read_text(encoding="utf-8"),
                                       out.with_suffix(".html"), title)
    return _result(out, viewer, title)


def convert_docx_network(customer: str, filename: str = "", data_b64: str = "",
                         log=None, should_cancel=None) -> dict:
    """Word (.docx) → Nemotron → network intake .xlsx → generated network map. Best-effort mapping;
    the resulting .xlsx is saved to network_input/ so the user can edit it and regenerate."""
    from atlas.sedraw import docx_to_network as d2n
    from atlas.sedraw.network_writer import write_network_topology
    nin = customers.customer_dir(customer) / "network_input"
    nin.mkdir(parents=True, exist_ok=True)
    safe = Path(filename or "intake.docx").name
    if not safe.lower().endswith(".docx"):
        safe += ".docx"
    try:
        raw = base64.b64decode((data_b64 or "").split(",")[-1])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"could not decode upload: {e}"}
    docx_path = nin / safe
    docx_path.write_bytes(raw)                          # keep the source .docx for provenance
    if log:
        log(f"📄 Reading {safe}…")
    text = d2n.extract_text(docx_path)
    net = d2n.parse_to_network(text, on_log=log, should_cancel=should_cancel)
    cleaned = _clean_network(net)
    if not cleaned["sites"]:
        return {"ok": False, "error": "Couldn't map a network topology from that document. "
                "Try the editor (＋ Create New) and fill it in by hand."}
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    xlsx = nin / f"{Path(safe).stem}_{ts}.xlsx"
    write_network_topology(cleaned, xlsx)
    n_cats = sum(len(s["categories"]) for s in cleaned["sites"])
    if log:
        log(f"🗺 Mapped {len(cleaned['sites'])} site(s) · {n_cats} device group(s). Generating the map…")
    res = generate_network(customer, xlsx.name)
    if not res.get("ok"):
        return res
    from urllib.parse import urlparse, unquote
    res["filename"] = xlsx.name
    res["sites"] = len(cleaned["sites"])
    res["categories"] = n_cats
    res["drawio_path"] = unquote(urlparse(res.get("drawio_uri", "")).path)
    res["viewer_uri"] = (res["drawio_uri"][:-7] + ".html") if res.get("drawio_uri", "").endswith(".drawio") else ""
    res["text"] = (f"Converted **{safe}** → {res['sites']} site(s), {n_cats} device group(s). "
                   f"Network map generated; the intake spreadsheet **{xlsx.name}** is editable in the tool.")
    return res


# ---- Vision Studio: free-form text → Nemotron → combined current/future diagram + history -------
def _vis_label(ts: str) -> str:
    if ts == "legacy":
        return "Legacy (imported)"
    try:
        return datetime.datetime.strptime(ts, "%Y%m%d_%H%M%S").strftime("%b %d, %Y · %I:%M %p")
    except Exception:
        return ts


def _vision_files(customer: str, ts: str):
    """Return (current_path|None, future_path|None) for a session timestamp."""
    cdir = customers.customer_dir(customer)
    vin = cdir / "vision_input"
    sl = vault.slug(customer)
    if ts == "legacy":
        cur, fut = vin / "current_state.xlsx", vin / "future_state.xlsx"
    else:
        cur, fut = vin / f"{sl}_current_{ts}.xlsx", vin / f"{sl}_future_{ts}.xlsx"
    return (cur if cur.exists() else None, fut if fut.exists() else None)


def _read_state(path):
    """Read one vision .xlsx → {'systems':[...], 'data_flows':[...]} (or empty)."""
    if not path or not path.exists():
        return {"systems": [], "data_flows": []}
    from atlas.sedraw.excel_reader import ExcelReader
    systems, flows = ExcelReader().read_vision_board(path)
    return {"systems": systems, "data_flows": flows}


def _build_combined(customer: str, ts: str):
    """(Re)build the combined .drawio + viewer from a session's input files. Returns _result dict + ts."""
    from atlas.sedraw.drawio_generator import VisionBoardGenerator
    cur_p, fut_p = _vision_files(customer, ts)
    cur, fut = _read_state(cur_p), _read_state(fut_p)
    states = []
    if cur["systems"]:
        states.append(("Current State", cur["systems"], cur["data_flows"]))
    if fut["systems"]:
        states.append(("Future State", fut["systems"], fut["data_flows"]))
    if not states:
        return {"ok": False, "error": "This session has no systems to draw."}
    cdir = customers.customer_dir(customer)
    out = cdir / "vision_output" / f"{vault.slug(customer)}_visionboard_{ts}.drawio"
    VisionBoardGenerator().generate_combined(customer, states, out)
    title = f"{customer} — Vision Board"
    viewer = diagram_view.write_viewer(out.read_text(encoding="utf-8"), out.with_suffix(".html"), title)
    res = _result(out, viewer, title)
    res["ts"] = ts
    res["counts"] = {"current_state": len(cur["systems"]), "future_state": len(fut["systems"])}
    res["drawio_path"] = str(out)
    res["viewer_path"] = str(viewer)
    cc, fc = len(cur["systems"]), len(fut["systems"])
    res["text"] = (f"Vision board for {customer} — current state {cc} system(s), "
                   f"future state {fc} system(s) (NVIDIA Nemotron).")
    return res


def vision_generate(customer: str, current_text: str = "", future_text: str = "", log=None) -> dict:
    """Free-form text → Nemotron → write the current/future .xlsx pair (new session) → combined diagram."""
    from atlas.sedraw import vision_ai, vision_writer
    data = vision_ai.generate_states(current_text, future_text, customer, on_log=log)
    if not data or not any((data.get(k) or {}).get("systems") for k in ("current_state", "future_state")):
        return {"ok": False, "error": "The AI couldn't extract any systems from that text — add more detail and retry."}
    cdir = customers.customer_dir(customer)
    sl = vault.slug(customer)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    for key, short in (("current_state", "current"), ("future_state", "future")):
        st = data.get(key) or {}
        if st.get("systems"):
            vision_writer.write_vision_state(
                st["systems"], st.get("data_flows", []),
                cdir / "vision_input" / f"{sl}_{short}_{ts}.xlsx")
    return _build_combined(customer, ts)


def vision_sessions(customer: str) -> list:
    """List saved vision sessions (newest first; the imported legacy pair, if any, last)."""
    import re as _re
    cdir = customers.customer_dir(customer)
    vin = cdir / "vision_input"
    sessions: dict = {}
    if vin.exists():
        for p in sorted(vin.glob("*.xlsx")):
            if p.name.startswith("~$"):
                continue
            m = _re.search(r"_(current|future)_(\d{8}_\d{6})\.xlsx$", p.name)
            if m:
                ts, which = m.group(2), m.group(1)
            elif p.name in ("current_state.xlsx", "future_state.xlsx"):
                ts, which = "legacy", ("current" if "current" in p.name else "future")
            else:
                continue
            s = sessions.setdefault(ts, {"has_current": False, "has_future": False})
            s["has_" + which] = True
    rows = [{"ts": ts, "label": _vis_label(ts), **flags} for ts, flags in sessions.items()]
    real = sorted([r for r in rows if r["ts"] != "legacy"], key=lambda r: r["ts"], reverse=True)
    return real + [r for r in rows if r["ts"] == "legacy"]


def vision_load(customer: str, ts: str = "") -> dict:
    """Load BOTH files of a session into the editable structure."""
    cur_p, fut_p = _vision_files(customer, ts)
    if not cur_p and not fut_p:
        return {"ok": False, "error": "Session not found."}
    return {"ok": True, "ts": ts, "label": _vis_label(ts),
            "current": _read_state(cur_p), "future": _read_state(fut_p),
            "statuses": VISION_STATUSES, "tiers": VISION_TIERS,
            "flow_types": VISION_FLOW_TYPES, "line_styles": VISION_LINE_STYLES}


def _recycle(files, category: str, key: str) -> int:
    """Soft-delete: move a set of files into vault/recyclebin/<category>/<key>/ (nothing erased —
    they vanish from the listings because those scan the live vault folders). Returns count moved."""
    import shutil
    import config
    binroot = config.RECYCLEBIN_DIR / category / key
    moved = 0
    for p in files:
        if p and p.exists():
            binroot.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(p), str(binroot / p.name))
                moved += 1
            except Exception:  # noqa: BLE001
                pass
    return moved


def vision_delete(customer: str, ts: str = "") -> dict:
    """Soft-delete a saved vision board (both Excel inputs + the generated .drawio/viewer) → recycle bin."""
    if not ts:
        return {"ok": False, "error": "missing session"}
    cdir = customers.customer_dir(customer)
    cur, fut = _vision_files(customer, ts)
    vout = cdir / "vision_output"
    outs = list(vout.glob(f"*{ts}*")) if vout.exists() else []
    files = [f for f in (cur, fut) if f] + outs
    if not files:
        return {"ok": False, "error": "session not found"}
    n = _recycle(files, "vision", f"{vault.slug(customer)}__{ts}")
    return {"ok": True, "ts": ts, "moved": n}


def network_delete(customer: str, filename: str = "") -> dict:
    """Soft-delete a network diagram: the input .xlsx + any generated .drawio/viewer → recycle bin."""
    if not filename:
        return {"ok": False, "error": "missing file"}
    cdir = customers.customer_dir(customer)
    src = cdir / "network_input" / filename
    stem = Path(filename).stem
    nout = cdir / "network_output"
    outs = list(nout.glob(f"*{stem}*")) if nout.exists() else []
    files = ([src] if src.exists() else []) + outs
    if not files:
        return {"ok": False, "error": "file not found"}
    n = _recycle(files, "network", f"{vault.slug(customer)}__{stem}")
    return {"ok": True, "filename": filename, "moved": n}


def _clean_vision_state(state: dict) -> dict:
    from atlas.sedraw import vision_ai
    systems = [vision_ai._fix_system(s) for s in (state or {}).get("systems", []) if isinstance(s, dict)]
    systems = [s for s in systems if s.get("system_name")]
    names = {s["system_name"] for s in systems}
    names_lower = {n.lower(): n for n in names}
    flows = []
    for f in (state or {}).get("data_flows", []):
        if isinstance(f, dict):
            fx = vision_ai._fix_flow(f, names, names_lower)
            if fx:
                flows.append(fx)
    return {"systems": systems, "data_flows": flows}


def vision_save(customer: str, ts: str = "", data: dict | None = None) -> dict:
    """Write edited current/future states back to the session's .xlsx files, then regenerate."""
    from atlas.sedraw import vision_writer
    data = data or {}
    cur = _clean_vision_state(data.get("current") or {})
    fut = _clean_vision_state(data.get("future") or {})
    if not cur["systems"] and not fut["systems"]:
        return {"ok": False, "error": "Add at least one system before saving."}
    cdir = customers.customer_dir(customer)
    sl = vault.slug(customer)
    # New sessions write to the {slug}_{which}_{ts}.xlsx pair; legacy writes back to its legacy names.
    if ts == "legacy":
        cur_path = cdir / "vision_input" / "current_state.xlsx"
        fut_path = cdir / "vision_input" / "future_state.xlsx"
    else:
        if not ts:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        cur_path = cdir / "vision_input" / f"{sl}_current_{ts}.xlsx"
        fut_path = cdir / "vision_input" / f"{sl}_future_{ts}.xlsx"
    if cur["systems"]:
        vision_writer.write_vision_state(cur["systems"], cur["data_flows"], cur_path)
    if fut["systems"]:
        vision_writer.write_vision_state(fut["systems"], fut["data_flows"], fut_path)
    return _build_combined(customer, ts)


def vision_view(customer: str, ts: str = "") -> dict:
    """(Re)render a session's combined diagram for viewing/download."""
    return _build_combined(customer, ts)


def generate_vision(customer: str, filename: str = "") -> dict:
    in_sub, out_sub = _KIND["vision"]
    cdir = customers.customer_dir(customer)
    files = _xlsx(cdir / in_sub)
    if not files:
        return {"ok": False, "error": "No vision board input .xlsx found for this customer."}
    src = _pick(files, filename)
    systems, flows = ExcelReader().read_vision_board(src)
    diagram_title = src.stem.replace("_", " ").title()   # current_state -> "Current State"
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    out = cdir / out_sub / f"{vault.slug(customer)}_{src.stem}_{ts}.drawio"
    VisionBoardGenerator().generate(customer, diagram_title, systems, flows, out)
    title = f"{customer} — {diagram_title}"
    viewer = diagram_view.write_viewer(out.read_text(encoding="utf-8"),
                                       out.with_suffix(".html"), title)
    return _result(out, viewer, title)
