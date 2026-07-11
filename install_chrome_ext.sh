#!/bin/zsh
# Try to install the unpacked Chrome extension through Chrome's own UI.
# Chrome intentionally has no public API for silent unpacked-extension installs,
# so this uses macOS UI automation and falls back to manual instructions.
set -euo pipefail

PROJECT_DIR="${0:A:h}"
EXT_DIR="${1:-$PROJECT_DIR/chrome-ext}"
CHROME_APP=""

log() { print -- "==> $*"; }
ok() { print -- "✓ $*"; }
warn() { print -- "⚠ $*"; }
die() { print -- "✗ $*" >&2; exit 1; }

manual_steps() {
  print ""
  print "Chrome extension manual step:"
  print "  1. Open chrome://extensions/"
  print "  2. Turn on Developer mode"
  print "  3. Click Load unpacked"
  print "  4. Select: $EXT_DIR"
}

find_chrome() {
  local candidate
  for candidate in "/Applications/Google Chrome.app" "$HOME/Applications/Google Chrome.app"; do
    if [[ -d "$candidate" ]]; then
      CHROME_APP="$candidate"
      return 0
    fi
  done

  if command -v mdfind >/dev/null 2>&1; then
    candidate="$(mdfind "kMDItemCFBundleIdentifier == 'com.google.Chrome'" 2>/dev/null | head -n 1 || true)"
    if [[ -n "$candidate" && -d "$candidate" ]]; then
      CHROME_APP="$candidate"
      return 0
    fi
  fi

  return 1
}

verify_loaded() {
  /usr/bin/python3 - "$EXT_DIR" <<'PY'
import json
import sys
from pathlib import Path

ext_dir = Path(sys.argv[1]).resolve()
chrome_root = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"

if not chrome_root.exists():
    sys.exit(1)

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
                    print(f"{profile_dir.name}:{extension_id}")
                    sys.exit(0)
            except OSError:
                continue

sys.exit(1)
PY
}

run_ui_automation() {
  /usr/bin/osascript - "$EXT_DIR" <<'APPLESCRIPT'
on textOfAttribute(theElement, attributeName)
  tell application "System Events"
    try
      return value of attribute attributeName of theElement as text
    on error
      return ""
    end try
  end tell
end textOfAttribute

on elementMatches(theElement, wanted)
  set wantedText to wanted as text
  set fieldsToCheck to {"AXTitle", "AXDescription", "AXHelp", "AXValue"}
  repeat with fieldName in fieldsToCheck
    set fieldValue to my textOfAttribute(theElement, fieldName)
    if fieldValue is wantedText then return true
  end repeat
  return false
end elementMatches

on findElement(theElement, wanted)
  tell application "System Events"
    if my elementMatches(theElement, wanted) then return theElement
    try
      set childElements to UI elements of theElement
    on error
      return missing value
    end try
  end tell

  repeat with childElement in childElements
    set foundElement to my findElement(childElement, wanted)
    if foundElement is not missing value then return foundElement
  end repeat

  return missing value
end findElement

on waitForElement(rootElement, wanted, secondsToWait)
  set startedAt to current date
  repeat while ((current date) - startedAt) < secondsToWait
    set foundElement to my findElement(rootElement, wanted)
    if foundElement is not missing value then return foundElement
    delay 0.25
  end repeat
  return missing value
end waitForElement

on waitForAnyElement(rootElement, wantedItems, secondsToWait)
  set startedAt to current date
  repeat while ((current date) - startedAt) < secondsToWait
    repeat with wanted in wantedItems
      set foundElement to my findElement(rootElement, wanted as text)
      if foundElement is not missing value then return foundElement
    end repeat
    delay 0.25
  end repeat
  return missing value
end waitForAnyElement

on pasteText(theText)
  set oldClipboard to the clipboard
  set the clipboard to theText
  tell application "System Events"
    keystroke "v" using {command down}
  end tell
  delay 0.2
  set the clipboard to oldClipboard
end pasteText

on run argv
set extDir to item 1 of argv

tell application "Google Chrome"
  activate
  open location "chrome://extensions/"
end tell

delay 1.5

tell application "System Events"
  if UI elements enabled is false then error "Accessibility automation is disabled for this app."
  tell process "Google Chrome"
    set frontmost to true
    set mainWindow to window 1

    set loadButtonNames to {"Load unpacked", "Load unpacked extension", "加载未打包的扩展程序", "加载已解压的扩展程序"}
    set developerModeNames to {"Developer mode", "开发者模式"}

    set loadButton to my waitForAnyElement(mainWindow, loadButtonNames, 2)
    if loadButton is missing value then
      set developerMode to my waitForAnyElement(mainWindow, developerModeNames, 6)
      if developerMode is missing value then error "Could not find the Developer mode control."
      click developerMode
      delay 1
      set loadButton to my waitForAnyElement(mainWindow, loadButtonNames, 8)
    end if

    if loadButton is missing value then error "Could not find the Load unpacked button."
    click loadButton
    delay 1

    keystroke "g" using {command down, shift down}
    delay 0.4
    my pasteText(extDir)
    key code 36
    delay 0.7
    key code 36
  end tell
end tell
end run
APPLESCRIPT
}

main() {
  [[ -d "$EXT_DIR" ]] || die "Extension folder not found: $EXT_DIR"

  if ! find_chrome; then
    warn "Google Chrome was not found. Skipping browser extension install."
    return 0
  fi

  log "Opening Google Chrome and loading unpacked extension"
  open -b "com.google.Chrome" "chrome://extensions/" >/dev/null 2>&1 || true

  if run_ui_automation; then
    local loaded=""
    local i
    for i in {1..10}; do
      loaded="$(verify_loaded 2>/dev/null || true)"
      if [[ -n "$loaded" ]]; then
        ok "Chrome extension is loaded ($loaded)"
        return 0
      fi
      sleep 0.5
    done
    ok "Chrome extension install flow completed"
    warn "Could not verify Chrome profile state yet; run ./doctor.sh to recheck."
  else
    warn "Chrome UI automation did not complete."
    warn "If macOS asks for Accessibility permission, grant it to your terminal app and rerun ./install_chrome_ext.sh"
    manual_steps
    return 1
  fi
}

main
