---
name: tts-say-installer
description: Install, diagnose, configure, repair, or uninstall the tts-say macOS AI-response text-to-speech tool. Use when a user asks an LLM agent to set up tts-say, fix no-audio issues, configure Claude Code or Codex hooks, load the Chrome extension, check MiniMax key/service status, expose tts-say through MCP, or understand the project installation workflow.
---

# tts-say Installer

## Goal

Help the user get tts-say working on macOS with the least manual configuration possible. tts-say has three layers:

- Local TTS service: `tts_server.py` launched by `~/Library/LaunchAgents/com.terri.tts-say.plist`.
- Agent/editor hooks: Claude Code Stop hook and Codex notify hook.
- Browser extension: unpacked Chrome MV3 extension in `chrome-ext/`.
- Trial relay: optional server-side MiniMax proxy in `relay/minimax_relay.py`.

Keep the shell installer as the source of truth for deterministic setup. Use MCP tools when available; otherwise run the repository scripts.

Default provider is MiniMax. For ordinary setup, copy `.env.example` to `.env` and configure `MINIMAX_API_KEY` there. If the user asks to use another TTS vendor, read `docs/PROVIDERS.md` before editing; provider changes belong in `tts_say.py` and diagnostics, not in Chrome extension or hook files.

## Locate The Project

Resolve the project directory before doing anything:

1. Use `TTS_SAY_HOME` if set.
2. Use the current working directory if it contains `tts_say.py`, `install.sh`, and `chrome-ext/manifest.json`.
3. Try `~/tts-say`.
4. Ask the user for the project path only if discovery fails.

Never assume the project lives at `/Users/a1/tts-say` on another machine.

## Preferred Workflow

1. Run diagnostics first.
   - If the tts-say MCP server is connected, call `doctor`.
   - Otherwise run `./doctor.sh --json --pretty`.
2. Explain only the meaningful failures or warnings.
3. Install or repair using the smallest safe action:
   - Full setup: `./install.sh`
   - No sound during setup: `./install.sh --no-test-audio`
   - Skip browser automation: `./install.sh --no-chrome-ext`
   - Chrome extension only: `./install_chrome_ext.sh`
   - Uninstall: `./uninstall.sh`
4. Run diagnostics again and confirm service, hooks, and Chrome extension status.

## MCP Usage

If the tts-say MCP server is configured, prefer these tools over shell commands:

- `doctor`
- `install`
- `install_chrome_extension`
- `uninstall`
- `start_service`
- `stop_service`
- `play_test_audio`
- `get_logs`

For full installation through MCP, call `install` with:

```json
{
  "test_audio": false,
  "chrome_extension": true,
  "hooks": true
}
```

Call `play_test_audio` only when the user expects sound or asks for an audio test.

## Safety Rules

- Do not print, summarize, or expose `MINIMAX_API_KEY`.
- Before modifying Claude or Codex config manually, create timestamped backups. Prefer `install.sh` because it already backs up supported files.
- Do not delete an existing Codex notify command; preserve it through `codex_notify_wrapper.sh` or let `install.sh` handle it.
- Do not force-install Chrome. If Google Chrome is not present, skip the browser extension step and say so.
- Browser extension installation may require macOS Accessibility permission. If UI automation fails, tell the user to grant permission to the current terminal/LLM app and rerun `./install_chrome_ext.sh`.
- Do not use destructive git or filesystem cleanup commands. Runtime files under `.runtime/` are safe to ignore.

## Diagnosis Hints

- `server_not_responding`: restart the LaunchAgent or run `./install.sh --no-test-audio --no-chrome-ext`.
- `missing_minimax_key`: ask the user to provide or add `MINIMAX_API_KEY` to project `.env`; do not invent a key.
- `using_macos_system_voice_fallback`: this is acceptable for a first-run demo; explain that MiniMax quality requires either the user's key or a trial relay token.
- `chrome_extension_not_loaded`: run `./install_chrome_ext.sh` if Chrome exists.
- `claude_hook_not_configured` or `codex_notify_not_configured`: run `./install.sh --no-test-audio --no-chrome-ext`.
- Need logs: use MCP `get_logs` or inspect `.runtime/server.err.log` and `.runtime/server.out.log`.
- Other TTS vendor requested: read `docs/PROVIDERS.md`; preserve MiniMax as the default path unless the user explicitly asks to change it.

## MCP Server Configuration

The bundled MCP server is at `mcp/tts_say_mcp.py`. A typical stdio config uses:

```json
{
  "command": "python3",
  "args": ["/absolute/path/to/tts-say/mcp/tts_say_mcp.py"]
}
```

After adding it to a client, reconnect the client and call `doctor` before changing anything.

## Trial Relay

Never place the owner's `MINIMAX_API_KEY` in the repository, installer, Chrome extension, MCP config, or user machine. If the user asks to let customers try MiniMax audio without their own key:

1. Point them to `docs/TRIAL_RELAY.md`.
2. Use `relay/minimax_relay.py` as the minimal server-side template.
3. Store only `TTS_SAY_RELAY_URL` and `TTS_SAY_TRIAL_TOKEN` on customer machines.
4. Keep macOS `say` fallback available when the relay is absent or over quota.
