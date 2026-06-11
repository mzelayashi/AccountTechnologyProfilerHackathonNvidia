#!/usr/bin/env bash
# Launch the standalone NeMo Guardrails Control Panel and open it in a clean app window.
# Used by the "NeMo Guardrails Panel" desktop shortcut. Separate from ATLAS — safe to run anytime.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
PORT="${GUARDRAILS_PORT:-8090}"
URL="http://localhost:${PORT}/"
PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"

# Start the panel server if it isn't already listening.
if ! curl -s -m2 -o /dev/null "$URL" 2>/dev/null; then
  nohup "$PY" guardrails_panel.py > /tmp/gpanel.log 2>&1 &
  for _ in $(seq 1 30); do curl -s -m1 -o /dev/null "$URL" 2>/dev/null && break; sleep 0.5; done
fi

# Open it: Chrome app-mode for a clean standalone window (like ATLAS); else the default browser.
if command -v google-chrome >/dev/null 2>&1; then
  exec google-chrome --app="$URL" --window-size=880,960 >/dev/null 2>&1
elif command -v chromium >/dev/null 2>&1; then
  exec chromium --app="$URL" --window-size=880,960 >/dev/null 2>&1
else
  exec xdg-open "$URL" >/dev/null 2>&1
fi
