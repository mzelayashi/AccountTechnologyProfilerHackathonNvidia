#!/usr/bin/env bash
# demo_health.sh — Pre-demo system check for ATLAS / NVIDIA Nemotron.
# Read-only. Proves the Nemotron-49B model is live on the 2x H100s and the stack is ready.
#   Usage:  ./demo_health.sh        (run it right before the demo)
# Config (override via env if needed):
PORT="${PORT:-8000}"                                   # vLLM OpenAI-compatible port
APP_PORT="${APP_PORT:-8080}"                           # ATLAS app server
MODEL="${MODEL:-Llama-3_3-Nemotron-Super-49B-v1_5}"
TP="${TP:-2}"                                          # tensor-parallel size (GPUs the model spans)
BASE="http://localhost:${PORT}/v1"
MGR="${MGR:-$HOME/vllm_service_manager.sh}"            # the vLLM start/stop/restart/recover manager

# ---- convenience flags: delegate to the vLLM service manager ----------------
# (no flag = read-only health check. These only ACT when you explicitly pass them.)
case "${1:-}" in
  --recover|-r) echo "→ Healing the Nemotron/vLLM service (quick recover: restarts only if down)…"
                exec bash "$MGR" <<< $'5\n9\n' ;;
  --restart)    echo "→ Force-restarting the Nemotron/vLLM service…"
                exec bash "$MGR" <<< $'4\n9\n' ;;
  --manage|-m)  exec bash "$MGR" ;;                    # open the full interactive menu
  --help|-h)    echo "Usage: ./demo_health.sh [--recover|--restart|--manage]   (no flag = health check)"
                exit 0 ;;
esac

# ---- colors (auto-off when not a terminal) ----------------------------------
if [ -t 1 ]; then
  G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; C=$'\e[36m'; B=$'\e[1m'; D=$'\e[2m'; M=$'\e[35m'; X=$'\e[0m'; CLR=$'\r\e[K'
else
  G=""; R=""; Y=""; C=""; B=""; D=""; M=""; X=""; CLR=""
fi
PASS=0; FAIL=0
COLS=64                                                # label column width before the status tag

line()  { printf '%s\n' "────────────────────────────────────────────────────────────────────"; }
# row "<label>" "<TAG>" <0|1 ok>  — prints label left, colored tag right-aligned
row() {
  local label="$1" tag="$2" ok="$3" color
  if [ "$ok" = "1" ]; then color="$G"; PASS=$((PASS+1)); else color="$R"; FAIL=$((FAIL+1)); fi
  local plain="${label}"
  local pad=$(( COLS - ${#plain} )); [ $pad -lt 1 ] && pad=1
  printf '  %s%*s%s%s%s\n' "$label" "$pad" "" "$color" "$tag" "$X"
}
note() { printf '     %s%s%s\n' "$D" "$1" "$X"; }
head2(){ printf '\n%s%s%s\n' "$C$B" "$1" "$X"; }
recovery_panel() {
  head2 "Recovery & controls  (handy if something goes down)"
  printf '  %s•%s heal the model (restart ONLY if down):  %s./demo_health.sh --recover%s\n'  "$G" "$X" "$C$B" "$X"
  printf '  %s•%s force-restart the model:                %s./demo_health.sh --restart%s\n'   "$G" "$X" "$C$B" "$X"
  printf '  %s•%s full model menu (start/stop/logs/…):    %sbash ~/vllm_service_manager.sh%s\n' "$G" "$X" "$C$B" "$X"
  printf '  %s•%s tail the model logs:                    %stail -f ~/vllm_manager_logs/vllm_server.log%s\n' "$G" "$X" "$C$B" "$X"
  printf '  %s•%s restart the ATLAS app:%s\n' "$G" "$X" "$X"
  printf '       %scd ~/ATLAS && nohup env ATLAS_COPILOT_DISABLED=1 ./.venv/bin/python run_atlas_linux.py > /tmp/atlas_run.log 2>&1 &%s\n' "$C" "$X"
}

# ---- banner -----------------------------------------------------------------
printf '\n%s' "$M$B"
cat <<'BANNER'
 ╔══════════════════════════════════════════════════════════════════╗
 ║   ATLAS  ·  NVIDIA Nemotron — Local Inference Pre-Demo Check       ║
 ╚══════════════════════════════════════════════════════════════════╝
BANNER
printf '%s' "$X"
printf '  %s%s  ·  host %s  ·  %s%s\n' "$D" "$(date '+%Y-%m-%d %H:%M:%S')" "$(hostname)" "endpoint ${BASE}" "$X"

# ---- 1) GPUs ----------------------------------------------------------------
head2 "1 · GPUs"
GPU_OK=0; H100=0; RESIDENT=0
if command -v nvidia-smi >/dev/null 2>&1; then
  SMI="$(nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu \
        --format=csv,noheader,nounits 2>/dev/null)"
  if [ -n "$SMI" ]; then
    while IFS=, read -r idx name mused mtot util temp; do
      idx="$(echo "$idx" | xargs)"; name="$(echo "$name" | xargs)"
      mused="$(echo "$mused" | xargs)"; mtot="$(echo "$mtot" | xargs)"
      util="$(echo "$util" | xargs)"; temp="$(echo "$temp" | xargs)"
      printf '  %sGPU %s%s  %s%-16s%s  mem %s%6s%s/%s MiB  util %3s%%  %s°C\n' \
        "$B" "$idx" "$X" "$C" "$name" "$X" "$G" "$mused" "$X" "$mtot" "$util" "$temp"
      echo "$name" | grep -qi "H100" && H100=$((H100+1))
      # weights resident if this GPU is holding >20 GiB (~20480 MiB)
      [ "${mused%.*}" -gt 20480 ] 2>/dev/null && RESIDENT=$((RESIDENT+1))
    done <<< "$SMI"
    if [ "$H100" -ge "$TP" ]; then row "${H100}× NVIDIA H100 detected" "✓ CONFIRMED" 1; GPU_OK=1
    else row "Expected ${TP}× H100, found ${H100}" "✗ CHECK" 0; fi
  else
    row "nvidia-smi returned no data" "✗ DOWN" 0
  fi
else
  row "nvidia-smi not found" "✗ DOWN" 0
fi

# ---- 2) Model resident across both H100s (TP proof) -------------------------
head2 "2 · Nemotron weights on the GPUs"
if [ "$RESIDENT" -ge "$TP" ]; then
  row "Nemotron-49B sharded across ${RESIDENT}× H100 · Tensor-Parallel = ${TP}" "✓ CONFIRMED" 1
  note "~$(( $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 | xargs) / 1024 )) GiB of model weights resident on EACH card — this is real, not a stub."
else
  row "Model not resident on ${TP} GPUs (found ${RESIDENT}) — is vLLM started?" "✗ DOWN" 0
fi

# ---- 3) vLLM inference engine ----------------------------------------------
head2 "3 · vLLM inference engine"
if curl -fs -m 5 "http://localhost:${PORT}/health" >/dev/null 2>&1; then
  row "vLLM /health" "● ACTIVE" 1
else
  row "vLLM /health (port ${PORT})" "✗ DOWN" 0
fi
MODELS_JSON="$(curl -fs -m 6 "${BASE}/models" 2>/dev/null)"
if [ -n "$MODELS_JSON" ]; then
  read -r MID MLEN <<< "$(printf '%s' "$MODELS_JSON" | python3 -c \
    "import sys,json;d=json.load(sys.stdin)['data'][0];print(d.get('id',''), d.get('max_model_len',''))" 2>/dev/null)"
  row "Serving model: ${MID:-unknown}" "● ACTIVE" 1
  note "OpenAI-compatible API · context window ${MLEN:-?} tokens"
else
  row "Model list endpoint (${BASE}/models)" "✗ DOWN" 0
fi

# ---- 4) Live generation (the proof it actually infers) ----------------------
head2 "4 · Live generation"
[ -t 1 ] && printf '  %srunning a live inference round-trip…%s\r' "$D" "$X"
GEN_TIMED="$(curl -fs -m 30 -w '\n%{time_total}' "${BASE}/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"system\",\"content\":\"detailed thinking off\"},{\"role\":\"user\",\"content\":\"Reply with exactly: NEMOTRON ONLINE\"}],\"max_tokens\":48,\"temperature\":0}" \
  2>/dev/null)"
SECS="$(printf '%s' "$GEN_TIMED" | tail -1)"
PARSED="$(printf '%s' "$GEN_TIMED" | sed '$d' | python3 -c '
import sys,json,re
try:
    d=json.load(sys.stdin)
    txt=d["choices"][0]["message"]["content"]
    txt=re.sub(r"<think>.*?</think>","",txt,flags=re.DOTALL).strip()
    u=d.get("usage",{})
    print("%s\t%s"%(txt[:60].replace(chr(10)," "), u.get("completion_tokens",0)))
except Exception as e:
    print("\t0")
')"
REPLY="$(printf '%s' "$PARSED" | cut -f1)"
CTOK="$(printf '%s' "$PARSED" | cut -f2)"
printf '%s' "$CLR"                                     # clear the "running…" progress line
if [ -n "$REPLY" ]; then
  row "Round-trip generation succeeded" "✓ CONFIRMED" 1
  TPS="?"
  if [ -n "$SECS" ] && [ -n "$CTOK" ]; then
    TPS="$(python3 -c "print(f'{($CTOK/$SECS):.1f}')" 2>/dev/null || echo '?')"
  fi
  note "model replied: \"${REPLY}\""
  note "latency $(printf '%.2f' "$SECS" 2>/dev/null || echo "$SECS")s · ${CTOK} tokens · ~${TPS} tok/s"
else
  row "Live generation request" "✗ DOWN" 0
fi

# ---- 5) ATLAS application (soft) -------------------------------------------
head2 "5 · ATLAS application"
if curl -fs -m 4 -o /dev/null "http://localhost:${APP_PORT}/" 2>/dev/null; then
  row "ATLAS web app (port ${APP_PORT})" "● ACTIVE" 1
else
  printf '  %s%-*s%s%s%s\n' "" "$COLS" "ATLAS app not running (optional — launch when ready)" "$Y" "○ OFFLINE" "$X"
fi

# ---- footer -----------------------------------------------------------------
printf '\n'; line
if [ "$FAIL" -eq 0 ]; then
  printf '  %s✅  ALL SYSTEMS GO — Nemotron-49B is live on %s× H100, ready to demo.%s\n' "$G$B" "$TP" "$X"
  line; recovery_panel; exit 0
else
  printf '  %s⚠  %d check(s) failed — review the red items above before demoing.%s\n' "$R$B" "$FAIL" "$X"
  printf '  %s→ quickest fix: %s./demo_health.sh --recover%s\n' "$Y" "$C$B" "$X"
  line; recovery_panel; exit 1
fi
