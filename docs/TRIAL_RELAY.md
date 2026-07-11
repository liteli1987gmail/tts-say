# Trial Relay

Users should never receive your `MINIMAX_API_KEY`. To let them try MiniMax-quality audio, run a small relay on your server:

```text
user machine -> tts-say local client -> your relay -> MiniMax
```

The user only stores:

```sh
TTS_SAY_RELAY_URL=https://your-domain.example/say
TTS_SAY_TRIAL_TOKEN=trial-token-you-issued
```

Your server stores:

```sh
MINIMAX_API_KEY=your-real-key
TTS_SAY_RELAY_TOKENS=trial-token-you-issued,another-token
```

## Minimal Relay

This repo includes a reference server:

```sh
MINIMAX_API_KEY=... \
TTS_SAY_RELAY_TOKENS=demo-user-1 \
PORT=8787 \
python3 relay/minimax_relay.py
```

Then configure a client:

```sh
cp .env.example .env
cat >> .env <<'EOF'
TTS_SAY_RELAY_URL=https://your-domain.example/say
TTS_SAY_TRIAL_TOKEN=demo-user-1
EOF
```

Run:

```sh
./doctor.sh --json --pretty
python3 tts_say.py "This is a trial relay test."
```

## Production Rules

- Use HTTPS.
- Issue unique trial tokens per user.
- Set daily character quotas.
- Rotate leaked or abused tokens.
- Do not log raw user text unless the user explicitly opts in.
- Add abuse controls before public launch: rate limits, token expiry, request size limits, and usage dashboards.
- Keep macOS `say` fallback enabled so users can still test the workflow if the relay is unavailable.
