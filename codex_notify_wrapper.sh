#!/bin/zsh
# Codex notify wrapper: optionally forwards the previous notify command, then
# reads the last assistant message aloud. The installer wires this script into
# ~/.codex/config.toml and passes the old notify command via --previous-notify.
set -u

PROJECT_DIR="${0:A:h}"
PAYLOAD="${@: -1}"
PREVIOUS_NOTIFY=""

i=1
while (( i <= $# )); do
  arg="${argv[$i]}"
  if [[ "$arg" == "--previous-notify" && $(( i + 1 )) -le $# ]]; then
    PREVIOUS_NOTIFY="${argv[$(( i + 1 ))]}"
    i=$(( i + 2 ))
  else
    i=$(( i + 1 ))
  fi
done

if [[ -n "$PREVIOUS_NOTIFY" ]]; then
  PREVIOUS_NOTIFY="$PREVIOUS_NOTIFY" PAYLOAD="$PAYLOAD" /usr/bin/python3 - <<'PY' &
import json
import os
import subprocess
import sys

try:
    command = json.loads(os.environ["PREVIOUS_NOTIFY"])
except (KeyError, json.JSONDecodeError):
    sys.exit(0)

if isinstance(command, str):
    command = [command]
if not isinstance(command, list) or not command:
    sys.exit(0)

payload = os.environ.get("PAYLOAD", "")
try:
    subprocess.Popen([str(part) for part in command] + [payload])
except OSError:
    pass
PY
fi

/usr/bin/python3 "$PROJECT_DIR/codex_notify_tts.py" "$PAYLOAD" &

wait
