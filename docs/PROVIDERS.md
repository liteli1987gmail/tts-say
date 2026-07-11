# TTS Providers

This project defaults to MiniMax. Other AI agents working on this repo should follow this rule:

```text
Default setup = configure MINIMAX_API_KEY in ~/.serenity_env.
Do not change Chrome extension, Claude hook, or Codex hook for provider changes.
Provider changes belong in the local TTS layer.
```

## Default Provider: MiniMax

For normal installs, ask the user to set:

```sh
MINIMAX_API_KEY=...
```

in:

```text
~/.serenity_env
```

The default MiniMax settings live in `tts_say.py`:

```python
VOICE_ID = "female-tianmei"
MODEL = "speech-02-hd"
```

The MiniMax API call is implemented in:

```text
tts_say.py -> synthesize_minimax()
```

## Existing Provider Modes

`tts_say.py` currently supports:

- `auto`: choose MiniMax when `MINIMAX_API_KEY` exists, else relay, else macOS fallback.
- `minimax`: require MiniMax.
- `relay`: call `TTS_SAY_RELAY_URL`, optionally with `TTS_SAY_TRIAL_TOKEN`.
- `macos`: use the built-in macOS `say` command.

Force a provider with:

```sh
TTS_SAY_PROVIDER=minimax
TTS_SAY_PROVIDER=relay
TTS_SAY_PROVIDER=macos
```

## Where To Modify For Another Vendor

To add another TTS vendor, modify these places:

1. `tts_say.py`
   - Add a new provider name in `choose_provider()`.
   - Add a new function, for example `synthesize_openai()` or `synthesize_elevenlabs()`.
   - Update `synthesize()` to route to the new function.
   - Return playable audio bytes when possible, then reuse `play_audio_bytes()`.

2. `tts_say_status.py`
   - Add provider-specific env detection.
   - Update `tts_provider.effective`.
   - Add warnings only when useful to an agent.

3. `doctor.sh`
   - Update the human-facing provider section.

4. `README.md` and this file
   - Document the new env vars and provider behavior.

5. `mcp/tts_say_mcp.py`
   - Usually no change is needed if the new provider is implemented behind `tts_say.py`.
   - Only update MCP if a provider needs a new explicit tool.

Do not change these files just to swap provider:

- `chrome-ext/content.js`
- `chrome-ext/background.js`
- `claude_stop_hook.py`
- `codex_notify_tts.py`
- `codex_notify_wrapper.sh`
- `tts_server.py`

Those components only pass text into the local TTS layer.

## Relay Is Preferred For Trials

If the product owner wants users to try a paid provider without exposing a secret key:

1. Keep the real vendor key on a server.
2. Expose a relay endpoint.
3. Put only `TTS_SAY_RELAY_URL` and `TTS_SAY_TRIAL_TOKEN` on the user machine.

See:

```text
docs/TRIAL_RELAY.md
relay/minimax_relay.py
```

## Security Rules

- Never commit real provider API keys.
- Never put provider keys into Chrome extension code.
- Never put provider keys into MCP config examples.
- Never print key values in diagnostics.
- Prefer server-side relay for product-owned trial keys.
