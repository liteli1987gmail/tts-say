#!/bin/zsh
# Uninstall tts-say service and editor hooks. Browser extensions must be removed
# from the browser UI because Chrome intentionally blocks silent removal.
set -euo pipefail

PROJECT_DIR="${0:A:h}"
LABEL="com.terri.tts-say"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
RUNTIME_DIR="$PROJECT_DIR/.runtime"
REMOVE_KEY=0

for arg in "$@"; do
  case "$arg" in
    --remove-key) REMOVE_KEY=1 ;;
    -h|--help)
      print "Usage: ./uninstall.sh [--remove-key]"
      exit 0
      ;;
    *)
      print "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

log() { print -- "==> $*"; }
ok() { print -- "✓ $*"; }
warn() { print -- "⚠ $*"; }

stop_audio() {
  local pid_file="$RUNTIME_DIR/afplay.pid"
  if [[ -f "$pid_file" ]]; then
    kill "$(cat "$pid_file")" >/dev/null 2>&1 || true
    rm -f "$pid_file"
  fi
}

remove_launch_agent() {
  log "Removing LaunchAgent"
  launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
  rm -f "$PLIST"
  ok "Removed $PLIST"
}

remove_claude_hook() {
  log "Removing Claude Code hook"
  /usr/bin/python3 - "$PROJECT_DIR" <<'PY'
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

project = Path(sys.argv[1])
settings = Path.home() / ".claude" / "settings.json"
needle = str(project / "claude_stop_hook.py")

if not settings.exists():
    print("not configured")
    sys.exit(0)

try:
    data = json.loads(settings.read_text())
except json.JSONDecodeError as exc:
    print(f"Claude settings is not valid JSON; skipped: {exc}", file=sys.stderr)
    sys.exit(0)

changed = False
hooks = data.get("hooks", {})
stop = hooks.get("Stop", [])
new_stop = []
for group in stop:
    if not isinstance(group, dict):
        new_stop.append(group)
        continue
    inner = group.get("hooks", [])
    if not isinstance(inner, list):
        new_stop.append(group)
        continue
    kept = []
    for hook in inner:
        command = str(hook.get("command", "")) if isinstance(hook, dict) else ""
        if needle in command:
            changed = True
        else:
            kept.append(hook)
    if kept:
        group["hooks"] = kept
        new_stop.append(group)
    else:
        changed = True

if changed:
    if new_stop:
        hooks["Stop"] = new_stop
    else:
        hooks.pop("Stop", None)
    if not hooks:
        data.pop("hooks", None)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(settings, settings.with_name(settings.name + f".tts-say.bak-{stamp}"))
    settings.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print("removed")
else:
    print("not found")
PY
  ok "Claude Code hook removal checked"
}

remove_codex_hook() {
  log "Removing Codex notify hook"
  /usr/bin/python3 - "$PROJECT_DIR" <<'PY'
import json
import re
import shutil
import sys
import tomllib
from datetime import datetime
from pathlib import Path

project = Path(sys.argv[1])
config = Path.home() / ".codex" / "config.toml"
wrapper = str(project / "codex_notify_wrapper.sh")

def toml_array(items):
    return "[" + ", ".join(json.dumps(str(item), ensure_ascii=False) for item in items) + "]"

def replace_notify(text, value):
    if value is None:
        lines = [line for line in text.splitlines() if not re.match(r"^notify\s*=", line)]
        return "\n".join(lines) + ("\n" if lines else "")
    line = "notify = " + toml_array(value)
    if re.search(r"(?m)^notify\s*=", text):
        return re.sub(r"(?m)^notify\s*=.*$", line, text, count=1)
    return line + "\n" + text

if not config.exists():
    print("not configured")
    sys.exit(0)

text = config.read_text()
try:
    parsed = tomllib.loads(text)
except tomllib.TOMLDecodeError as exc:
    print(f"Codex config is not valid TOML; skipped: {exc}", file=sys.stderr)
    sys.exit(0)

notify = parsed.get("notify")
if not isinstance(notify, list):
    print("no notify array")
    sys.exit(0)

changed = False
restored = None

if wrapper in [str(item) for item in notify]:
    if "--previous-notify" in notify:
        index = notify.index("--previous-notify")
        if index + 1 < len(notify):
            try:
                restored = json.loads(notify[index + 1])
            except json.JSONDecodeError:
                restored = None
    changed = True
else:
    # Handles configs where another notifier stored tts-say as its previous notify.
    cleaned = []
    i = 0
    while i < len(notify):
        if notify[i] == "--previous-notify" and i + 1 < len(notify) and wrapper in str(notify[i + 1]):
            changed = True
            i += 2
            continue
        cleaned.append(notify[i])
        i += 1
    restored = cleaned if changed else notify

if not changed:
    print("not found")
    sys.exit(0)

new_text = replace_notify(text, restored)
stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
shutil.copy2(config, config.with_name(config.name + f".tts-say.bak-{stamp}"))
config.write_text(new_text)
print("removed")
PY
  ok "Codex notify hook removal checked"
}

remove_key_if_requested() {
  [[ "$REMOVE_KEY" == "1" ]] || return 0
  local env_file="$PROJECT_DIR/.env"
  [[ -f "$env_file" ]] || return 0
  log "Removing MINIMAX_API_KEY from $env_file"
  /usr/bin/python3 - "$env_file" <<'PY'
import shutil
import sys
from datetime import datetime
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text().splitlines()
new_lines = [line for line in lines if not line.startswith("MINIMAX_API_KEY=")]
if new_lines != lines:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, path.with_name(path.name + f".tts-say.bak-{stamp}"))
    path.write_text("\n".join(new_lines) + ("\n" if new_lines else ""))
PY
  ok "MiniMax key removal checked"
}

main() {
  stop_audio
  remove_launch_agent
  remove_claude_hook
  remove_codex_hook
  remove_key_if_requested
  print ""
  warn "Remove the Chrome extension manually from chrome://extensions/ if you loaded it."
  ok "tts-say uninstall finished"
}

main
