#!/usr/bin/env bash
# Start ATLAS (local web server) and open it in the browser.
# Reuses an already-running server on :8080 instead of starting a second one.
cd "$(dirname "$(readlink -f "$0")")"
URL="http://127.0.0.1:8080/"

echo " ============================================================"
echo "   SHI ATLAS  —  starting…"
echo " ============================================================"

# Open the browser once the server answers (works whether we start it or it's already up).
(
  for _ in $(seq 1 40); do
    curl -s -o /dev/null "$URL" 2>/dev/null && break
    sleep 0.5
  done
  # App Mode: a borderless, tabless window (no address bar) — looks like a standalone desktop app.
  # Dedicated --user-data-dir keeps it its own window/profile (1320x880 matches the Windows build).
  CH_ARGS="--app=$URL --window-size=1320,880 --user-data-dir=$HOME/.atlas-app --no-first-run --no-default-browser-check"
  (google-chrome $CH_ARGS >/dev/null 2>&1 \
     || google-chrome-stable $CH_ARGS >/dev/null 2>&1 \
     || xdg-open "$URL" >/dev/null 2>&1) &
) &

if curl -s -o /dev/null "$URL" 2>/dev/null; then
  echo " ATLAS is already running → $URL  (opening browser)"
  echo
  read -p " This window isn't needed — press Enter to close it."
else
  echo " Launching server → $URL"
  echo " (Keep this window open while you use ATLAS; close it to stop the server.)"
  echo
  exec ./.venv/bin/python run_atlas_linux.py
fi
