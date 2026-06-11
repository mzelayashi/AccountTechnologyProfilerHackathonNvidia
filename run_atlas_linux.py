"""SHI ATLAS — Linux launcher (no pywebview/WebView2).

Mirrors atlas_web.py:main() but skips the native desktop window, which depends on
Windows-only pywebview/pythonnet/pywin32. Instead it serves the exact same local HTTP
server on a fixed port and lets you open the UI in a normal browser.

Launch:  .venv/bin/python run_atlas_linux.py
Then open:  http://127.0.0.1:8080/
"""
from __future__ import annotations

import logging
import os
import threading
from http.server import ThreadingHTTPServer

# TEMPORARY: disable the Copilot/Chrome (Selenium) engine on this machine. With this set, ATLAS
# never opens a browser — all inference calls return a stub until the Nemotron engine replaces them
# (see NEMOTRON_ARCHITECTURE.md). Must be set BEFORE importing atlas modules that read it.
os.environ.setdefault("ATLAS_COPILOT_DISABLED", "1")

import atlas.skills  # noqa: F401,E402  (registers all skills on import)
from atlas.store import artifacts
from atlas.web.api import Api
from atlas.web.server import make_handler

logging.getLogger("pywebview").setLevel(logging.CRITICAL)

HOST = "127.0.0.1"
PORT = 8080


def main() -> None:
    try:                                  # every trip-report .md becomes a first-class artifact
        n = artifacts.backfill_trip_reports()
        if n:
            print(f"[backfill] registered {n} trip report(s) as artifacts", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[backfill] skipped: {e}", flush=True)

    api = Api()
    srv = ThreadingHTTPServer((HOST, PORT), make_handler(api))
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    # Cron scheduler + calendar auto-refresh are intentionally NOT started: both drive Microsoft 365
    # Copilot through Chrome, which is disabled on this machine (ATLAS_COPILOT_DISABLED). They will
    # be re-enabled once the Nemotron engine replaces the browser engine.
    print("[engine] Copilot/Chrome engine DISABLED — no browser windows; "
          "scheduler & calendar auto-refresh off.", flush=True)

    print(f"\n  ATLAS running →  http://{HOST}:{PORT}/\n  (Ctrl+C to stop)\n", flush=True)
    try:
        threading.Event().wait()          # block forever; server runs in the daemon thread
    except KeyboardInterrupt:
        print("\n[atlas] shutting down", flush=True)
        try:
            api.shutdown()
        except Exception:  # noqa: BLE001
            pass
        srv.shutdown()


if __name__ == "__main__":
    main()
