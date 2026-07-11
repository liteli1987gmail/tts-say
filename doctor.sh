#!/bin/zsh
# Check whether tts-say is installed and reachable.
set -u

PROJECT_DIR="${0:A:h}"
if [[ "${1:-}" == "--json" ]]; then
  shift
  exec env PYTHONDONTWRITEBYTECODE=1 python3 "$PROJECT_DIR/tts_say_status.py" "$@"
fi

LABEL="com.terri.tts-say"
PORT="48765"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
RUNTIME_DIR="$PROJECT_DIR/.runtime"
FAILURES=0

ok() { print -- "✓ $*"; }
warn() { print -- "⚠ $*"; }
fail() { print -- "✗ $*"; FAILURES=$(( FAILURES + 1 )); }
section() { print ""; print -- "==> $*"; }

check_command() {
  if command -v "$1" >/dev/null 2>&1; then
    ok "$1 found"
  else
    fail "$1 missing"
  fi
}

section "System"
[[ "$(uname -s)" == "Darwin" ]] && ok "macOS detected" || fail "This machine is not macOS"
check_command python3
check_command afplay
check_command say
check_command curl

section "Project Files"
for file in .env.example tts_say.py tts_server.py claude_stop_hook.py codex_notify_tts.py codex_notify_wrapper.sh install_chrome_ext.sh chrome-ext/manifest.json relay/minimax_relay.py docs/TRIAL_RELAY.md docs/PROVIDERS.md; do
  [[ -f "$PROJECT_DIR/$file" ]] && ok "$file exists" || fail "$file missing"
done

section "TTS Provider"
if [[ -f "$PROJECT_DIR/.env" ]] && grep -Eq '^MINIMAX_API_KEY=.+$' "$PROJECT_DIR/.env"; then
  ok "MiniMax key found in .env"
elif [[ -f "$PROJECT_DIR/.env" ]] && grep -Eq '^TTS_SAY_RELAY_URL=.+$' "$PROJECT_DIR/.env"; then
  ok "Trial relay URL found in .env"
elif [[ -f "$HOME/.serenity_env" ]] && grep -Eq '^MINIMAX_API_KEY=.+$' "$HOME/.serenity_env"; then
  ok "MiniMax key found in legacy ~/.serenity_env"
elif [[ -f "$HOME/.serenity_env" ]] && grep -Eq '^TTS_SAY_RELAY_URL=.+$' "$HOME/.serenity_env"; then
  ok "Trial relay URL found in legacy ~/.serenity_env"
elif command -v say >/dev/null 2>&1; then
  warn "MiniMax key not found; copy .env.example to .env and fill it in, or use macOS system voice for first-run demos"
else
  fail "No MiniMax key, trial relay, or macOS say fallback available"
fi

section "Syntax"
if python3 -m py_compile "$PROJECT_DIR/tts_say.py" "$PROJECT_DIR/tts_server.py" "$PROJECT_DIR/claude_stop_hook.py" "$PROJECT_DIR/codex_notify_tts.py"; then
  ok "Python files compile"
else
  fail "Python compile check failed"
fi
if python3 -m json.tool "$PROJECT_DIR/chrome-ext/manifest.json" >/dev/null; then
  ok "Chrome manifest is valid JSON"
else
  fail "Chrome manifest JSON is invalid"
fi

section "Service"
[[ -f "$PLIST" ]] && ok "LaunchAgent plist exists" || fail "LaunchAgent plist missing: $PLIST"
if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  ok "LaunchAgent is loaded"
else
  fail "LaunchAgent is not loaded"
fi
if curl -fsS "http://127.0.0.1:$PORT/ping" >/dev/null 2>&1; then
  ok "Local server responds at http://127.0.0.1:$PORT/ping"
else
  fail "Local server did not respond"
  if [[ -f "$RUNTIME_DIR/server.err.log" ]]; then
    print ""
    print "Recent server errors:"
    tail -n 20 "$RUNTIME_DIR/server.err.log"
  fi
fi

section "Claude / Codex Hooks"
if [[ -f "$HOME/.claude/settings.json" ]] && grep -q 'claude_stop_hook.py' "$HOME/.claude/settings.json"; then
  ok "Claude Code Stop hook references tts-say"
else
  warn "Claude Code Stop hook not found"
fi
if [[ -f "$HOME/.codex/config.toml" ]] && grep -Eq 'codex_notify_wrapper\.sh|codex_notify_tts\.py' "$HOME/.codex/config.toml"; then
  ok "Codex notify references tts-say"
else
  warn "Codex notify hook not found"
fi

section "Browser Extension"
if [[ -d "/Applications/Google Chrome.app" || -d "$HOME/Applications/Google Chrome.app" ]]; then
  ok "Google Chrome found"
  ok "Automated installer: $PROJECT_DIR/install_chrome_ext.sh"
  loaded_extension="$(python3 - "$PROJECT_DIR/chrome-ext" <<'PY'
import json
import sys
from pathlib import Path

ext_dir = Path(sys.argv[1]).resolve()
chrome_root = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
matches = []

if chrome_root.exists():
    for profile_dir in chrome_root.iterdir():
        if not profile_dir.is_dir():
            continue
        for name in ("Preferences", "Secure Preferences"):
            pref_file = profile_dir / name
            if not pref_file.exists():
                continue
            try:
                data = json.loads(pref_file.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            settings = data.get("extensions", {}).get("settings", {})
            if not isinstance(settings, dict):
                continue
            for extension_id, extension in settings.items():
                if not isinstance(extension, dict):
                    continue
                path = extension.get("path")
                if not path:
                    continue
                try:
                    if Path(path).expanduser().resolve() == ext_dir:
                        matches.append(f"{profile_dir.name}:{extension_id}")
                except OSError:
                    pass

print("\\n".join(sorted(set(matches))))
PY
)"
  if [[ -n "$loaded_extension" ]]; then
    ok "Chrome extension appears loaded: $loaded_extension"
  else
    warn "Chrome extension path not found in Chrome profiles yet"
  fi
else
  warn "Google Chrome not found; browser extension install will be skipped"
fi
ok "Extension folder: $PROJECT_DIR/chrome-ext"

print ""
if (( FAILURES == 0 )); then
  ok "Doctor passed"
  exit 0
else
  fail "Doctor found $FAILURES problem(s)"
  exit 1
fi
