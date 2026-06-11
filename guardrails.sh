#!/usr/bin/env bash
# guardrails.sh — turn the ATLAS command-box NeMo Guardrails rail ON / OFF (or check status).
#
#   ./guardrails.sh on        # enable the input rail (on-topic + safety + anti prompt-injection)
#   ./guardrails.sh off       # disable it (default — command box runs unguarded)
#   ./guardrails.sh status    # show current state
#
# Flips the `guardrails_enabled` setting in the vault. The running ATLAS app reads settings fresh on
# every command, so the change takes effect on the NEXT command — no restart needed. Fail-open: even
# enabled, any guardrails error lets the request through, so it can't break a live demo.

cd "$(dirname "$0")" || exit 1
PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
action="${1:-status}"

if [ -t 1 ]; then G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; B=$'\e[1m'; X=$'\e[0m'; else G=""; Y=""; C=""; B=""; X=""; fi

_state() { "$PY" -c "from atlas.store import settings; print('on' if settings.load().get('guardrails_enabled') else 'off')" 2>/dev/null; }
_set()   { "$PY" -c "from atlas.store import settings; settings.save({'guardrails_enabled': $1}); print('ok')" 2>/dev/null; }

case "$action" in
  on)
    [ "$(_set True)" = "ok" ] || { echo "could not write setting"; exit 1; }
    printf '%s🛡️  Guardrails ENABLED%s\n' "$G$B" "$X"
    printf '   The command box now keeps the brain on-topic (your customers + tech research) and\n'
    printf '   politely refuses off-topic / unsafe / prompt-injection input.\n'
    printf '   %sTakes effect on the next command (no restart). Adds ~3–6s per command (a real rail check).%s\n' "$C" "$X"
    ;;
  off)
    [ "$(_set False)" = "ok" ] || { echo "could not write setting"; exit 1; }
    printf '%s🛡️  Guardrails DISABLED%s  (default — command box runs unguarded, full speed)\n' "$Y$B" "$X"
    ;;
  status)
    if [ "$(_state)" = "on" ]; then printf '%s🛡️  Guardrails: ON%s\n' "$G$B" "$X"
    else printf '%s🛡️  Guardrails: OFF%s\n' "$Y$B" "$X"; fi
    ;;
  *)
    echo "Usage: ./guardrails.sh [on|off|status]"; exit 1 ;;
esac
