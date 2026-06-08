"""SHI ATLAS — WebView2 (Edge Chromium) shell over a local HTTP server.

Launch:  python atlas_web.py   (or START.bat)
"""
from __future__ import annotations

import logging
import threading
from http.server import ThreadingHTTPServer

import webview

import atlas.skills  # noqa: F401  (registers all skills on import)
from atlas.store import artifacts
from atlas.web.api import Api
from atlas.web.server import make_handler

logging.getLogger("pywebview").setLevel(logging.CRITICAL)


def main() -> None:
    try:                                  # every trip-report .md becomes a first-class artifact
        n = artifacts.backfill_trip_reports()
        if n:
            print(f"[backfill] registered {n} trip report(s) as artifacts", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[backfill] skipped: {e}", flush=True)
    api = Api()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(api))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    try:                                  # fire scheduled instructions (Cron Jobs tab) while open
        from atlas.jobs.scheduler import start_calendar_autorefresh, start_scheduler
        start_scheduler()
        start_calendar_autorefresh()      # re-gather the 3 calendar days every 30 min
    except Exception as e:  # noqa: BLE001
        print(f"[cron] scheduler not started: {e}", flush=True)

    window = webview.create_window(
        "SHI ATLAS",
        url=f"http://127.0.0.1:{port}/",
        width=1320,
        height=880,
        min_size=(1040, 700),
        background_color="#080b11",
    )
    window.events.closed += api.shutdown
    webview.start()


if __name__ == "__main__":
    main()
