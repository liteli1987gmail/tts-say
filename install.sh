#!/bin/zsh
# Install tts-say on macOS.
set -euo pipefail

PROJECT_DIR="${0:A:h}"
LABEL="com.terri.tts-say"
PORT="48765"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
ENV_FILE="$HOME/.serenity_env"
RUNTIME_DIR="$PROJECT_DIR/.runtime"

RUN_TEST_AUDIO=1
OPEN_BROWSER=1
CONFIGURE_HOOKS=1
INSTALL_CHROME_EXT=1
REQUIRE_MINIMAX_KEY=0

for arg in "$@"; do
  case "$arg" in
    --no-test-audio) RUN_TEST_AUDIO=0 ;;
    --no-open-browser) OPEN_BROWSER=0; INSTALL_CHROME_EXT=0 ;;
    --no-chrome-ext) INSTALL_CHROME_EXT=0 ;;
    --no-hooks) CONFIGURE_HOOKS=0 ;;
    --require-minimax-key) REQUIRE_MINIMAX_KEY=1 ;;
    -h|--help)
      print "Usage: ./install.sh [--no-test-audio] [--no-open-browser] [--no-chrome-ext] [--no-hooks] [--require-minimax-key]"
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
die() { print -- "✗ $*" >&2; exit 1; }

backup_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  local stamp
  stamp="$(date +%Y%m%d-%H%M%S)"
  cp "$file" "$file.tts-say.bak-$stamp"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"
}

ensure_macos() {
  [[ "$(uname -s)" == "Darwin" ]] || die "tts-say currently supports macOS only."
}

ensure_dependencies() {
  log "Checking local dependencies"
  require_command python3
  require_command afplay
  require_command curl
  [[ -f "$PROJECT_DIR/tts_say.py" ]] || die "Cannot find $PROJECT_DIR/tts_say.py"
  [[ -f "$PROJECT_DIR/tts_server.py" ]] || die "Cannot find $PROJECT_DIR/tts_server.py"
  ok "python3, afplay, curl are available"
}

ensure_minimax_key() {
  log "Checking TTS provider"
  if [[ -f "$ENV_FILE" ]] && grep -q '^MINIMAX_API_KEY=' "$ENV_FILE"; then
    ok "Found MINIMAX_API_KEY in $ENV_FILE"
    return
  fi
  if [[ -f "$ENV_FILE" ]] && grep -q '^TTS_SAY_RELAY_URL=' "$ENV_FILE"; then
    ok "Found TTS_SAY_RELAY_URL in $ENV_FILE"
    return
  fi

  if [[ "$REQUIRE_MINIMAX_KEY" != "1" ]]; then
    warn "MiniMax key not found. First-run demo will use macOS system voice."
    warn "Add MINIMAX_API_KEY or TTS_SAY_RELAY_URL later for MiniMax-quality audio."
    return
  fi

  if [[ ! -t 0 ]]; then
    die "MINIMAX_API_KEY is missing. Add it to $ENV_FILE, then run ./install.sh again."
  fi

  print -n "Enter MINIMAX_API_KEY: "
  stty -echo
  read key
  stty echo
  print
  [[ -n "$key" ]] || die "Empty MINIMAX_API_KEY"

  touch "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  {
    print ""
    print "# Added by tts-say installer"
    print "MINIMAX_API_KEY=$key"
  } >> "$ENV_FILE"
  ok "Saved MINIMAX_API_KEY to $ENV_FILE"
}

write_launch_agent() {
  log "Installing LaunchAgent"
  mkdir -p "$HOME/Library/LaunchAgents" "$RUNTIME_DIR"
  backup_file "$PLIST"
  /usr/bin/python3 - "$PLIST" "$PROJECT_DIR/tts_server.py" "$RUNTIME_DIR/server.out.log" "$RUNTIME_DIR/server.err.log" <<'PY'
import plistlib
import sys
from pathlib import Path

plist_path = Path(sys.argv[1])
server_path = Path(sys.argv[2])
stdout_path = Path(sys.argv[3])
stderr_path = Path(sys.argv[4])

data = {
    "Label": "com.terri.tts-say",
    "ProgramArguments": ["/usr/bin/python3", str(server_path)],
    "RunAtLoad": True,
    "KeepAlive": True,
    "StandardOutPath": str(stdout_path),
    "StandardErrorPath": str(stderr_path),
}
plist_path.write_bytes(plistlib.dumps(data, sort_keys=False))
PY
  ok "Wrote $PLIST"
}

restart_service() {
  log "Starting local TTS service"
  launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  launchctl enable "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  launchctl kickstart -k "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true

  local i
  for i in {1..30}; do
    if curl -fsS "http://127.0.0.1:$PORT/ping" >/dev/null 2>&1; then
      ok "Service is healthy at http://127.0.0.1:$PORT"
      return
    fi
    sleep 0.2
  done

  warn "Service did not respond yet. Recent error log:"
  tail -n 20 "$RUNTIME_DIR/server.err.log" 2>/dev/null || true
  die "Local TTS service failed to start"
}

configure_claude() {
  log "Configuring Claude Code Stop hook"
  /usr/bin/python3 - "$PROJECT_DIR" <<'PY'
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

project = Path(sys.argv[1])
settings = Path.home() / ".claude" / "settings.json"
command = f"python3 {project / 'claude_stop_hook.py'}"
hook = {
    "type": "command",
    "command": command,
    "timeout": 15,
    "statusMessage": "合成语音朗读中...",
}

settings.parent.mkdir(parents=True, exist_ok=True)
if settings.exists():
    try:
        data = json.loads(settings.read_text())
    except json.JSONDecodeError as exc:
        print(f"Claude settings is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
else:
    data = {}

hooks = data.setdefault("hooks", {})
stop = hooks.setdefault("Stop", [])
changed = False
found = False

for group in stop:
    if not isinstance(group, dict):
        continue
    inner = group.setdefault("hooks", [])
    if not isinstance(inner, list):
        group["hooks"] = inner = []
    for existing in inner:
        if isinstance(existing, dict) and "claude_stop_hook.py" in str(existing.get("command", "")):
            found = True
            if existing != hook:
                existing.clear()
                existing.update(hook)
                changed = True

if not found:
    stop.append({"hooks": [hook]})
    changed = True

if changed:
    if settings.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(settings, settings.with_name(settings.name + f".tts-say.bak-{stamp}"))
    settings.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print("updated")
else:
    print("already configured")
PY
  ok "Claude Code hook is configured"
}

configure_codex() {
  log "Configuring Codex notify hook"
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

def contains_tts(value):
    return "codex_notify_wrapper.sh" in json.dumps(value, ensure_ascii=False) or "codex_notify_tts.py" in json.dumps(value, ensure_ascii=False)

config.parent.mkdir(parents=True, exist_ok=True)
text = config.read_text() if config.exists() else ""

try:
    parsed = tomllib.loads(text) if text.strip() else {}
except tomllib.TOMLDecodeError as exc:
    print(f"Codex config is not valid TOML; skipped notify update: {exc}", file=sys.stderr)
    sys.exit(0)

existing = parsed.get("notify")
if contains_tts(existing):
    print("already references tts-say; left unchanged")
    sys.exit(0)

new_notify = ["/bin/zsh", wrapper]
if existing:
    new_notify.extend(["--previous-notify", json.dumps(existing, ensure_ascii=False)])

line = "notify = " + toml_array(new_notify)
if re.search(r"(?m)^notify\s*=", text):
    new_text = re.sub(r"(?m)^notify\s*=.*$", line, text, count=1)
else:
    new_text = line + "\n" + text

if new_text != text:
    if config.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(config, config.with_name(config.name + f".tts-say.bak-{stamp}"))
    config.write_text(new_text)
    print("updated")
else:
    print("already configured")
PY
  ok "Codex notify hook is configured or already present"
}

play_test_audio() {
  [[ "$RUN_TEST_AUDIO" == "1" ]] || return 0
  log "Playing a test sentence"
  /usr/bin/python3 "$PROJECT_DIR/tts_say.py" "tts-say 安装完成。以后 AI 回复结束后，我会自动朗读。"
  ok "Test audio finished"
}

install_chrome_extension() {
  [[ "$INSTALL_CHROME_EXT" == "1" ]] || return 0
  log "Installing Chrome extension when Google Chrome is available"
  if "$PROJECT_DIR/install_chrome_ext.sh"; then
    ok "Chrome extension step completed"
  else
    warn "Chrome extension step needs manual confirmation; the local service and hooks are already installed."
    [[ "$OPEN_BROWSER" == "1" ]] && open "$PROJECT_DIR/chrome-ext" >/dev/null 2>&1 || true
  fi
}

main() {
  ensure_macos
  ensure_dependencies
  ensure_minimax_key
  write_launch_agent
  restart_service
  if [[ "$CONFIGURE_HOOKS" == "1" ]]; then
    configure_claude
    configure_codex
  fi
  play_test_audio
  install_chrome_extension
  print ""
  ok "tts-say install finished. Run ./doctor.sh any time to verify the setup."
}

main
