"""Tiny localhost HTTP server backing the WebView2 UI (avoids the js_api bridge).

Serves index.html + the loading video, and exposes the Api methods as POST /api/<name>
with a JSON body of kwargs. The page uses fetch() — robust, no cross-thread bridge.
"""
from __future__ import annotations

import json
import mimetypes
import urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import config

_WEB = Path(__file__).resolve().parent
_LOADING = _WEB.parent / "loading"
# File types served from the vault via GET /vaultfile (inline SE Draw diagram viewers, etc.)
_VAULT_OK_EXT = {".html", ".drawio", ".svg", ".json", ".png", ".txt", ".md"}


def make_handler(api):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silence
            pass

        # ---- helpers ----
        def _raw(self, code, data: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            # Never let WebView2/Edge cache the UI — otherwise a relaunch can serve a STALE index.html
            # (new Python backend, old front-end). Always fetch fresh so code changes show on relaunch.
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            try:
                self.wfile.write(data)
            except Exception:
                pass

        def _file(self, p: Path):
            if not p.exists() or not p.is_file():
                return self._raw(404, b"not found", "text/plain")
            data = p.read_bytes()
            ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes="):
                try:
                    s, _, e = rng[6:].partition("-")
                    start = int(s)
                    end = int(e) if e else len(data) - 1
                    chunk = data[start:end + 1]
                    return self._raw(206, chunk, ctype, {
                        "Content-Range": f"bytes {start}-{end}/{len(data)}",
                        "Accept-Ranges": "bytes"})
                except Exception:
                    pass
            self._raw(200, data, ctype, {"Accept-Ranges": "bytes"})

        # ---- routes ----
        def _vaultfile(self):
            # Serve a file from inside the vault, sandboxed to VAULT_DIR (no path escape).
            qs = urllib.parse.urlparse(self.path).query
            rel = urllib.parse.parse_qs(qs).get("p", [""])[0]
            base = config.VAULT_DIR.resolve()
            try:
                target = (base / rel).resolve()
            except Exception:
                return self._raw(400, b"bad path", "text/plain")
            if target != base and base not in target.parents:
                return self._raw(403, b"forbidden", "text/plain")
            if target.suffix.lower() not in _VAULT_OK_EXT:
                return self._raw(403, b"forbidden type", "text/plain")
            return self._file(target)

        def _drawioview(self):
            # Render a vault .drawio through the diagrams.net viewer (sandboxed to VAULT_DIR).
            qs = urllib.parse.urlparse(self.path).query
            rel = urllib.parse.parse_qs(qs).get("p", [""])[0]
            base = config.VAULT_DIR.resolve()
            try:
                target = (base / rel).resolve()
            except Exception:
                return self._raw(400, b"bad path", "text/plain")
            if target != base and base not in target.parents:
                return self._raw(403, b"forbidden", "text/plain")
            if target.suffix.lower() != ".drawio" or not target.is_file():
                return self._raw(403, b"not a drawio", "text/plain")
            from atlas.artifacts import diagram_view
            try:
                page = diagram_view.render_html(target.read_text(encoding="utf-8"), target.stem)
            except Exception:
                return self._raw(404, b"unreadable", "text/plain")
            self._raw(200, page.encode("utf-8"), "text/html; charset=utf-8")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                return self._file(_WEB / "index.html")
            if path == "/vaultfile":
                return self._vaultfile()
            if path == "/drawioview":
                return self._drawioview()
            if path.startswith("/loading/"):
                return self._file(_LOADING / Path(path).name)
            cand = _WEB / path.lstrip("/")
            if cand.exists() and cand.is_file():
                return self._file(cand)
            self._raw(404, b"not found", "text/plain")

        def do_POST(self):
            if not self.path.startswith("/api/"):
                return self._raw(404, b"{}", "application/json")
            name = self.path[len("/api/"):].split("?")[0]
            ln = int(self.headers.get("Content-Length") or 0)
            try:
                args = json.loads(self.rfile.read(ln) or b"{}") if ln else {}
            except Exception:
                args = {}
            fn = getattr(api, name, None)
            if not callable(fn) or name.startswith("_"):
                return self._raw(404, b"{}", "application/json")
            try:
                result = fn(**args) if isinstance(args, dict) else fn()
            except Exception as e:  # noqa: BLE001
                result = {"error": str(e)}
            self._raw(200, json.dumps(result).encode("utf-8"), "application/json")

    return Handler
