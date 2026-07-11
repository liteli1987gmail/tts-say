# tts-say

[中文文档](README.zh-CN.md)

tts-say reads AI responses aloud and turns AI-heavy reading workflows into a listening experience.

It supports three entry points:

- Claude Code Stop hook
- Codex notify hook
- Chrome extension for ChatGPT, Claude, Gemini, DeepSeek, Doubao, Kimi, and similar web apps

The default TTS provider is MiniMax. First-run demos can use the built-in macOS `say` voice. Product trials can use a private relay for MiniMax audio.

## Install

```sh
git clone https://github.com/liteli1987gmail/tts-say.git
cd tts-say
./install.sh
```

The installer handles:

- macOS, Python, `afplay`, `say`, and `curl` checks
- `MINIMAX_API_KEY` detection in `~/.serenity_env`
- macOS `say` voice for first-run demos
- LaunchAgent installation at `~/Library/LaunchAgents/com.terri.tts-say.plist`
- local service check at `http://127.0.0.1:48765/ping`
- Claude Code Stop hook setup
- Codex notify hook setup with existing notify preservation
- one short test sentence
- Chrome extension page automation when Google Chrome is installed

Chrome loads unpacked extensions through `chrome://extensions/`. `install.sh` uses macOS UI automation for this step. The manual path is:

1. Open `chrome://extensions/`
2. Enable Developer mode
3. Click Load unpacked
4. Select the `chrome-ext` folder

Retry Chrome extension setup:

```sh
./install_chrome_ext.sh
```

When macOS asks for Accessibility permission, allow the current terminal app to control the computer in System Settings, then rerun the command.

## Common Commands

```sh
./doctor.sh
```

Checks the service, config, Chrome extension files, TTS provider, and MiniMax key. When the Chrome extension is loaded, diagnostics show the Chrome profile and extension id.

```sh
./doctor.sh --json --pretty
```

Prints structured diagnostics for LLM/MCP clients. The output reports key presence only.

```sh
./uninstall.sh
```

Removes the LaunchAgent and Claude/Codex hooks. The Chrome extension can be removed from `chrome://extensions/`.

```sh
./install.sh --no-test-audio
./install.sh --no-open-browser
./install.sh --no-chrome-ext
```

These options skip the test sentence, Chrome page automation, or Chrome extension setup.

## Manual Usage

```sh
python3 tts_say.py "Hello, I will read this aloud."
echo "Text from stdin" | python3 tts_say.py
python3 tts_say.py --no-interrupt "Queue this after the previous audio."
```

TTS provider order:

1. Use MiniMax when `MINIMAX_API_KEY` exists.
2. Use a trial relay when `TTS_SAY_RELAY_URL` exists, optionally with `TTS_SAY_TRIAL_TOKEN`.
3. Use the macOS `say` voice for first-run demos.

Force a provider:

```sh
TTS_SAY_PROVIDER=macos python3 tts_say.py "Use the built-in macOS voice."
TTS_SAY_PROVIDER=relay python3 tts_say.py "Use my trial relay."
TTS_SAY_PROVIDER=minimax python3 tts_say.py "Require MiniMax."
```

MiniMax is the default provider. AI agents adding another TTS provider should read [docs/PROVIDERS.md](docs/PROVIDERS.md). Provider logic belongs in `tts_say.py` and diagnostics. The Chrome extension, Claude hook, and Codex hook pass text into the local TTS layer.

Local service:

```sh
curl http://127.0.0.1:48765/ping
curl -X POST http://127.0.0.1:48765/say \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello from tts-say"}'
```

## Project Layout

- `tts_say.py`: text cleanup, provider selection, MiniMax/relay/macOS playback
- `tts_server.py`: local HTTP service used by the browser extension
- `tts_say_status.py`: structured diagnostics for `doctor.sh --json` and MCP
- `claude_stop_hook.py`: reads the last Claude Code assistant message aloud
- `codex_notify_tts.py`: reads the last Codex assistant message aloud
- `codex_notify_wrapper.sh`: Codex notify wrapper with existing notify preservation
- `chrome-ext/`: Chrome MV3 extension
- `install.sh`: installer
- `install_chrome_ext.sh`: Chrome UI automation for unpacked extension loading
- `doctor.sh`: diagnostics
- `uninstall.sh`: uninstaller
- `mcp/tts_say_mcp.py`: stdio MCP server for LLM clients
- `skills/tts-say-installer/`: install and repair skill for Codex/LLM clients
- `relay/minimax_relay.py`: private trial relay template with server-side MiniMax key
- `docs/TRIAL_RELAY.md`: trial relay deployment notes
- `docs/PROVIDERS.md`: provider extension notes

## Config And Trials

The installer creates timestamped backups before changing existing config:

- `~/.claude/settings.json.tts-say.bak-YYYYMMDD-HHMMSS`
- `~/.codex/config.toml.tts-say.bak-YYYYMMDD-HHMMSS`
- `~/Library/LaunchAgents/com.terri.tts-say.plist.tts-say.bak-YYYYMMDD-HHMMSS`

The recommended MiniMax trial path is a relay:

```text
user machine -> tts-say local client -> your relay -> MiniMax
```

The user machine stores:

```sh
TTS_SAY_RELAY_URL=https://your-domain.example/say
TTS_SAY_TRIAL_TOKEN=demo-user-token
```

The real `MINIMAX_API_KEY` stays in your server environment. See [docs/TRIAL_RELAY.md](docs/TRIAL_RELAY.md).

## LLM Client Integration

This project provides both a skill and an MCP server.

Skill path:

```text
skills/tts-say-installer
```

Clients that support Codex skills can copy or link this folder into their skills directory. The skill teaches an LLM how to locate the project, run diagnostics, install the service, configure Claude/Codex hooks, load the Chrome extension, and handle MiniMax keys safely.

MCP server path:

```text
mcp/tts_say_mcp.py
```

Typical stdio config:

```json
{
  "mcpServers": {
    "tts-say": {
      "command": "python3",
      "args": ["/absolute/path/to/tts-say/mcp/tts_say_mcp.py"]
    }
  }
}
```

MCP tools:

- `doctor`
- `install`
- `install_chrome_extension`
- `uninstall`
- `start_service`
- `stop_service`
- `play_test_audio`
- `get_logs`

Ask the LLM to call `doctor` first, then choose the smallest repair action from the structured status.
