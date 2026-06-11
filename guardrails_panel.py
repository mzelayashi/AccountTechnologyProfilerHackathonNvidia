#!/usr/bin/env python3
"""Standalone NeMo Guardrails Control Panel — runs OUTSIDE the ATLAS app, on its own port.

A tiny stdlib web app (no new dependencies) that exposes the command-box guardrail's levers, a live
test box, and a recent-blocks log. It reads/writes the SAME `guardrails_*` settings the ATLAS app
reads, so it genuinely governs the live command-box rail — but as a separate process: if this panel
crashes or you close it, the ATLAS server is completely unaffected.

    Run:   ./guardrails_panel.sh         (or  .venv/bin/python guardrails_panel.py)
    Open:  http://localhost:8090/
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # import the atlas package + config

from atlas.brain import guardrails
from atlas.store import settings

PORT = int(os.getenv("GUARDRAILS_PORT", "8090"))
_BOOL_KEYS = {"guardrails_enabled", "guardrails_topical", "guardrails_safety", "guardrails_injection"}
_STR_KEYS = {"guardrails_strictness"}
_FREE_STR_KEYS = {"guardrails_blocked_terms", "guardrails_blocked_domains"}

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Guardrails Control Panel</title>
<style>
*{box-sizing:border-box} body{margin:0;background:#0a0f17;color:#e6edf3;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:26px 20px 60px}
h1{font-size:22px;margin:0 0 2px} .sub{color:#8b949e;font-size:12.5px;margin-bottom:18px}
.card{background:#0d1622;border:1px solid #1e2a3a;border-radius:14px;padding:16px 18px;margin-bottom:16px}
.hd{font-size:12px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:#56d4dd;margin-bottom:10px}
.row{display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:1px solid #141f2e}
.row:last-child{border-bottom:0} .row .lbl{flex:1} .row .lbl b{font-weight:600} .row .lbl .d{color:#8b949e;font-size:12px}
.badge{font-size:11px;font-weight:700;padding:2px 9px;border-radius:20px}
.on{background:#0e2a1b;color:#3fb950;border:1px solid #1f5132} .off{background:#2a1316;color:#ff7b72;border:1px solid #5b2026}
.sw{position:relative;width:46px;height:26px;flex:0 0 auto;cursor:pointer}
.sw input{display:none} .sw .tr{position:absolute;inset:0;background:#30363d;border-radius:20px;transition:.2s}
.sw .kb{position:absolute;top:3px;left:3px;width:20px;height:20px;background:#fff;border-radius:50%;transition:.2s}
.sw input:checked+.tr{background:#238636} .sw input:checked+.tr+.kb{transform:translateX(20px)}
select{background:#0c121b;border:1px solid #28435f;border-radius:8px;color:#e6edf3;font:inherit;padding:7px 10px}
.txt{width:100%;margin-top:6px;background:#0c121b;border:1px solid #28435f;border-radius:8px;color:#e6edf3;font:inherit;padding:8px 10px}
textarea{width:100%;background:#0c121b;border:1px solid #28435f;border-radius:10px;color:#e6edf3;font:inherit;padding:11px;min-height:64px;resize:vertical}
button.go{background:#163049;border:1px solid #1f4d77;color:#fff;border-radius:9px;padding:9px 16px;cursor:pointer;font:inherit;margin-top:8px}
button.go:hover{background:#1c416b}
.result{margin-top:10px;padding:10px 12px;border-radius:10px;font-size:13px;display:none}
.result.allow{display:block;background:#0e2a1b;border:1px solid #1f5132}
.result.refuse{display:block;background:#2a1316;border:1px solid #5b2026}
.tag{font-size:10.5px;color:#8b949e}
.blk{padding:8px 0;border-bottom:1px solid #141f2e;font-size:13px} .blk:last-child{border-bottom:0}
.blk .t{color:#ff9a9a} .blk .m{color:#8b949e;font-size:11.5px}
.muted{color:#6e7681;font-size:11px} code{color:#9fd0ff}
.disabledwarn{color:#d29922;font-size:12px;margin-top:6px}
</style></head><body><div class="wrap">
<h1>🛡️ NeMo Guardrails — Control Panel</h1>
<div class="sub">Standalone · governs the ATLAS command-box rail · runs separately so it can't affect the demo app</div>

<div class="card">
  <div class="hd">Engine</div>
  <div id="engine" class="muted">loading…</div>
</div>

<div class="card">
  <div class="hd">Levers</div>
  <div class="row"><div class="lbl"><b>Master switch</b><div class="d">Enable the guardrail on the ATLAS command box</div></div>
    <span id="b_enabled" class="badge off">OFF</span>
    <label class="sw"><input type="checkbox" id="guardrails_enabled" onchange="setKey(this)"><span class="tr"></span><span class="kb"></span></label></div>
  <div class="row"><div class="lbl"><b>🎯 Keep on-topic</b><div class="d">Refuse off-topic chatter (poems, recipes, unrelated coding)</div></div>
    <label class="sw"><input type="checkbox" id="guardrails_topical" onchange="setKey(this)"><span class="tr"></span><span class="kb"></span></label></div>
  <div class="row"><div class="lbl"><b>🚫 Block unsafe</b><div class="d">Refuse harmful / malicious / dangerous requests</div></div>
    <label class="sw"><input type="checkbox" id="guardrails_safety" onchange="setKey(this)"><span class="tr"></span><span class="kb"></span></label></div>
  <div class="row"><div class="lbl"><b>🛡️ Block prompt-injection</b><div class="d">Refuse jailbreaks ("ignore your instructions", "reveal your prompt")</div></div>
    <label class="sw"><input type="checkbox" id="guardrails_injection" onchange="setKey(this)"><span class="tr"></span><span class="kb"></span></label></div>
  <div class="row"><div class="lbl"><b>Strictness</b><div class="d">How aggressively to refuse borderline input</div></div>
    <select id="guardrails_strictness" onchange="setKey(this)">
      <option value="lenient">Lenient</option><option value="balanced">Balanced</option><option value="strict">Strict</option></select></div>
  <div class="row" style="display:block">
    <div class="lbl"><b>🚫 Blocked words / phrases</b><div class="d">Refuse any command containing these (comma-separated). Applies on the command box when the master switch is on.</div></div>
    <input type="text" id="guardrails_blocked_terms" onchange="setKey(this)" placeholder="e.g. reddit, 4chan, competitor name" class="txt"></div>
  <div class="row" style="display:block">
    <div class="lbl"><b>🌐 Blocked research sources</b><div class="d">The web-research agent skips these domains (comma-separated). Always active.</div></div>
    <input type="text" id="guardrails_blocked_domains" onchange="setKey(this)" placeholder="e.g. reddit.com, quora.com" class="txt"></div>
  <div id="offwarn" class="disabledwarn"></div>
  <div style="margin-top:14px;border-top:1px solid #141f2e;padding-top:12px;display:flex;align-items:center;gap:12px">
    <button class="go" onclick="saveAll()">💾 Save settings</button>
    <span id="saved" class="tag"></span>
  </div>
  <div class="muted" style="margin-top:6px">Changes apply on your next command — no restart needed. (Each toggle also saves instantly; Save just confirms everything, including the text boxes.)</div>
</div>

<div class="card">
  <div class="hd">Live test</div>
  <div class="muted" style="margin-bottom:8px">Try any phrase — evaluated with the current levers (works even when the master switch is off).</div>
  <textarea id="testin" placeholder="e.g. write me a poem  ·  which customers use Palo Alto?  ·  ignore your instructions"></textarea>
  <button class="go" onclick="runTest()">Test</button>
  <div id="testres" class="result"></div>
</div>

<div class="card">
  <div class="hd">Recent blocks</div>
  <div id="blocks" class="muted">none yet</div>
</div>
</div>
<script>
// Render engine status, master badge, and the Recent-blocks log. Does NOT touch the lever input
// fields — so the 4s live poll never clobbers what you're typing.
function renderStatus(s){
  const st=s.status, lv=st.levers;
  document.getElementById('engine').innerHTML =
    `Active engine: <b style="color:#3fb950">${st.engine}</b> · NeMo Guardrails package: ${st.package_available?'<b style="color:#3fb950">installed</b>':'<span style="color:#ff7b72">not found (native fallback)</span>'}<br>`+
    `<span class="tag">model <code>${st.model}</code> · endpoint <code>${st.endpoint}</code></span>`;
  const b=document.getElementById('b_enabled'); b.textContent=lv.enabled?'ON':'OFF'; b.className='badge '+(lv.enabled?'on':'off');
  document.getElementById('offwarn').textContent = lv.enabled?'' : '⚠ Master switch is OFF — the ATLAS command box is currently unguarded (you can still test below).';
  const bl=s.recent||[];
  document.getElementById('blocks').innerHTML = bl.length ? bl.map(x=>
    `<div class="blk"><div class="t">⛔ ${esc(x.text)}</div><div class="m">${x.at} · ${x.engine} · ${x.source} · ${esc(x.reason)}</div></div>`).join('') : 'none yet';
}
async function load(){           // full load: also sets the lever controls (init + after explicit actions)
  const s=await (await fetch('/state')).json();
  const lv=s.status.levers;
  for(const k of ['guardrails_enabled','guardrails_topical','guardrails_safety','guardrails_injection']){
    const key=k.replace('guardrails_',''); document.getElementById(k).checked=!!lv[key]; }
  document.getElementById('guardrails_strictness').value=lv.strictness||'balanced';
  document.getElementById('guardrails_blocked_terms').value=lv.blocked_terms||'';
  document.getElementById('guardrails_blocked_domains').value=lv.blocked_domains||'';
  renderStatus(s);
}
async function refreshLog(){     // lightweight live poll — Recent blocks + status only (no input clobber)
  try{ const s=await (await fetch('/state')).json(); renderStatus(s); }catch(e){}
}
setInterval(refreshLog, 4000);
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
async function setKey(el){
  const value = el.type==='checkbox' ? el.checked : el.value;
  await fetch('/set',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:el.id,value})});
  load();
}
async function saveAll(){
  const sv=document.getElementById('saved'); sv.textContent='saving…';
  const ids=['guardrails_enabled','guardrails_topical','guardrails_safety','guardrails_injection',
             'guardrails_strictness','guardrails_blocked_terms','guardrails_blocked_domains'];
  for(const id of ids){
    const el=document.getElementById(id);
    const value = el.type==='checkbox' ? el.checked : el.value;
    await fetch('/set',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:id,value})});
  }
  await load();
  sv.style.color='#3fb950'; sv.textContent='✓ Saved · active on your next command';
  setTimeout(()=>{sv.textContent='';},4000);
}
async function runTest(){
  const text=document.getElementById('testin').value.trim(); if(!text)return;
  const r=document.getElementById('testres'); r.className='result'; r.style.display='block'; r.textContent='checking…';
  const d=await (await fetch('/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})})).json();
  r.className='result '+(d.allowed?'allow':'refuse');
  r.innerHTML = (d.allowed?'✅ <b>ALLOWED</b>':'⛔ <b>REFUSED</b>')+` &nbsp;<span class="tag">${d.engine} · ${esc(d.reason)}</span>`;
  load();
}
load();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}") if n else {}
        except Exception:
            return {}

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if path == "/state":
            return self._send(200, json.dumps({"status": guardrails.status(),
                                               "recent": guardrails.recent_blocks()}))
        self._send(404, "{}")

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/set":
            d = self._body(); key = d.get("key"); value = d.get("value")
            if key in _BOOL_KEYS:
                settings.save({key: bool(value)})
            elif key in _STR_KEYS and value in ("lenient", "balanced", "strict"):
                settings.save({key: value})
            elif key in _FREE_STR_KEYS:
                settings.save({key: str(value or "")[:500]})
            else:
                return self._send(400, json.dumps({"ok": False, "error": "unknown lever"}))
            return self._send(200, json.dumps({"ok": True}))
        if path == "/test":
            return self._send(200, json.dumps(guardrails.test(self._body().get("text", ""))))
        self._send(404, "{}")


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"\n  🛡️  Guardrails Control Panel  →  http://localhost:{PORT}/")
    print(f"  (separate process — closing this does NOT affect the ATLAS app. Ctrl+C to stop.)\n", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[guardrails-panel] stopped.")
        srv.shutdown()


if __name__ == "__main__":
    main()
