#!/usr/bin/env bash
# guardrails_panel.sh — launch the standalone Guardrails Control Panel (separate from the ATLAS app).
#   ./guardrails_panel.sh
# Opens a small web UI (default http://localhost:8090/) with the guardrail levers, a live test box,
# and a recent-blocks log. It governs the SAME setting the ATLAS command box reads, but runs as its
# own process — closing it never affects ATLAS. Ctrl+C to stop.
cd "$(dirname "$0")" || exit 1
PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
exec "$PY" guardrails_panel.py
