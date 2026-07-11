#!/usr/bin/env python3
"""Structured diagnostics for tts-say.

This module is shared by doctor.sh and the MCP server so agents can read stable
JSON instead of scraping human-facing terminal output.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
LABEL = "com.terri.tts-say"
PORT = 48765
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
RUNTIME_DIR = PROJECT_DIR / ".runtime"
ENV_FILE = Path.home() / ".serenity_env"


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run(command: list[str], timeout: float = 5) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def file_contains(path: Path, needle: str) -> bool:
    try:
        return needle in path.read_text(errors="replace")
    except OSError:
        return False


def has_minimax_key() -> bool:
    try:
        for line in ENV_FILE.read_text(errors="replace").splitlines():
            if line.startswith("MINIMAX_API_KEY=") and line.split("=", 1)[1].strip():
                return True
    except OSError:
        return False
    return bool(os.environ.get("MINIMAX_API_KEY"))


def env_value(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name].strip()
    try:
        for line in ENV_FILE.read_text(errors="replace").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def python_syntax_ok(path: Path) -> tuple[bool, str]:
    try:
        ast.parse(path.read_text())
    except (OSError, SyntaxError) as exc:
        return False, str(exc)
    return True, ""


def json_ok(path: Path) -> tuple[bool, str]:
    try:
        json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return False, str(exc)
    return True, ""


def service_responds() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/ping", timeout=2) as resp:
            return resp.status == 200 and json.loads(resp.read()).get("ok") is True
    except Exception:
        return False


def launch_agent_loaded() -> bool:
    code, _, _ = run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"])
    return code == 0


def find_chrome_apps() -> list[str]:
    candidates = [
        Path("/Applications/Google Chrome.app"),
        Path.home() / "Applications" / "Google Chrome.app",
    ]
    found = [str(path) for path in candidates if path.exists()]
    if found or not command_exists("mdfind"):
        return found

    code, stdout, _ = run(["mdfind", "kMDItemCFBundleIdentifier == 'com.google.Chrome'"], timeout=8)
    if code == 0:
        for line in stdout.splitlines():
            path = Path(line)
            if path.exists() and str(path) not in found:
                found.append(str(path))
    return found


def chrome_extension_matches() -> list[dict[str, str]]:
    ext_dir = (PROJECT_DIR / "chrome-ext").resolve()
    chrome_root = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    matches: list[dict[str, str]] = []
    if not chrome_root.exists():
        return matches

    for profile_dir in chrome_root.iterdir():
        if not profile_dir.is_dir():
            continue
        for name in ("Preferences", "Secure Preferences"):
            pref_file = profile_dir / name
            if not pref_file.exists():
                continue
            try:
                data = json.loads(pref_file.read_text(errors="replace"))
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
                        item = {
                            "profile": profile_dir.name,
                            "extension_id": extension_id,
                            "path": str(ext_dir),
                            "source_file": name,
                        }
                        if item not in matches:
                            matches.append(item)
                except OSError:
                    continue
    return matches


def tail(path: Path, lines: int = 40) -> list[str]:
    try:
        return path.read_text(errors="replace").splitlines()[-lines:]
    except OSError:
        return []


def collect_status(include_logs: bool = False) -> dict[str, Any]:
    required_files = [
        "tts_say.py",
        "tts_server.py",
        "claude_stop_hook.py",
        "codex_notify_tts.py",
        "codex_notify_wrapper.sh",
        "install.sh",
        "install_chrome_ext.sh",
        "uninstall.sh",
        "doctor.sh",
        "chrome-ext/manifest.json",
        "relay/minimax_relay.py",
        "docs/TRIAL_RELAY.md",
        "docs/PROVIDERS.md",
    ]
    python_files = [
        "tts_say.py",
        "tts_server.py",
        "claude_stop_hook.py",
        "codex_notify_tts.py",
        "tts_say_status.py",
        "relay/minimax_relay.py",
    ]

    syntax = {}
    for file_name in python_files:
        ok, error = python_syntax_ok(PROJECT_DIR / file_name)
        syntax[file_name] = {"ok": ok, "error": error}

    manifest_ok, manifest_error = json_ok(PROJECT_DIR / "chrome-ext" / "manifest.json")

    minimax_key_present = has_minimax_key()
    relay_url_present = bool(env_value("TTS_SAY_RELAY_URL"))
    macos_fallback_present = command_exists("say")
    if minimax_key_present:
        effective_provider = "minimax"
    elif relay_url_present:
        effective_provider = "relay"
    elif macos_fallback_present:
        effective_provider = "macos"
    else:
        effective_provider = "none"

    status: dict[str, Any] = {
        "ok": True,
        "project_dir": str(PROJECT_DIR),
        "platform": {
            "is_macos": sys.platform == "darwin",
            "python": sys.executable,
        },
        "commands": {name: command_exists(name) for name in ("python3", "afplay", "say", "curl", "launchctl")},
        "files": {file_name: (PROJECT_DIR / file_name).exists() for file_name in required_files},
        "minimax": {
            "env_file": str(ENV_FILE),
            "key_present": minimax_key_present,
        },
        "relay": {
            "url_present": relay_url_present,
            "trial_token_present": bool(env_value("TTS_SAY_TRIAL_TOKEN")),
        },
        "tts_provider": {
            "effective": effective_provider,
            "macos_fallback_present": macos_fallback_present,
        },
        "syntax": syntax,
        "chrome_manifest": {
            "ok": manifest_ok,
            "error": manifest_error,
        },
        "service": {
            "port": PORT,
            "plist": str(PLIST),
            "plist_exists": PLIST.exists(),
            "launch_agent_loaded": launch_agent_loaded(),
            "responds": service_responds(),
        },
        "hooks": {
            "claude_settings": str(Path.home() / ".claude" / "settings.json"),
            "claude_configured": file_contains(Path.home() / ".claude" / "settings.json", "claude_stop_hook.py"),
            "codex_config": str(Path.home() / ".codex" / "config.toml"),
            "codex_configured": (
                file_contains(Path.home() / ".codex" / "config.toml", "codex_notify_wrapper.sh")
                or file_contains(Path.home() / ".codex" / "config.toml", "codex_notify_tts.py")
            ),
        },
        "chrome": {
            "apps": find_chrome_apps(),
            "extension_dir": str((PROJECT_DIR / "chrome-ext").resolve()),
            "extension_loaded": chrome_extension_matches(),
        },
    }

    failures = []
    if not status["platform"]["is_macos"]:
        failures.append("not_macos")
    for command, present in status["commands"].items():
        if not present:
            failures.append(f"missing_command:{command}")
    for file_name, present in status["files"].items():
        if not present:
            failures.append(f"missing_file:{file_name}")
    if not status["minimax"]["key_present"]:
        if not status["relay"]["url_present"] and not status["commands"].get("say"):
            failures.append("no_tts_provider_available")
    for file_name, result in status["syntax"].items():
        if not result["ok"]:
            failures.append(f"python_syntax:{file_name}")
    if not status["chrome_manifest"]["ok"]:
        failures.append("chrome_manifest_invalid")
    if not status["service"]["plist_exists"]:
        failures.append("launch_agent_plist_missing")
    if not status["service"]["launch_agent_loaded"]:
        failures.append("launch_agent_not_loaded")
    if not status["service"]["responds"]:
        failures.append("server_not_responding")

    status["failures"] = failures
    status["warnings"] = []
    if status["chrome"]["apps"] and not status["chrome"]["extension_loaded"]:
        status["warnings"].append("chrome_extension_not_loaded")
    if status["tts_provider"]["effective"] == "macos":
        status["warnings"].append("using_macos_system_voice_fallback")
    if not status["hooks"]["claude_configured"]:
        status["warnings"].append("claude_hook_not_configured")
    if not status["hooks"]["codex_configured"]:
        status["warnings"].append("codex_notify_not_configured")
    status["ok"] = not failures

    if include_logs:
        status["logs"] = {
            "server_err": tail(RUNTIME_DIR / "server.err.log"),
            "server_out": tail(RUNTIME_DIR / "server.out.log"),
        }

    return status


def main() -> int:
    include_logs = "--logs" in sys.argv
    pretty = "--pretty" in sys.argv
    status = collect_status(include_logs=include_logs)
    print(json.dumps(status, ensure_ascii=False, indent=2 if pretty else None))
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
