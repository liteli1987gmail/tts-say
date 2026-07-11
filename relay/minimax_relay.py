#!/usr/bin/env python3
"""Minimal MiniMax TTS relay for private trials.

Run this on your own server. Never ship MINIMAX_API_KEY to users.

Required env:
  MINIMAX_API_KEY=...
  TTS_SAY_RELAY_TOKENS=token1,token2

Optional env:
  PORT=8787
  TTS_SAY_RELAY_DAILY_CHARS=20000
  TTS_SAY_RELAY_STATE=/tmp/tts-say-relay-usage.json
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODEL = os.environ.get("MINIMAX_TTS_MODEL", "speech-02-hd")
VOICE_ID = os.environ.get("MINIMAX_TTS_VOICE_ID", "female-tianmei")
PORT = int(os.environ.get("PORT", "8787"))
MAX_CHARS = int(os.environ.get("TTS_SAY_RELAY_MAX_CHARS", "3000"))
DAILY_CHARS = int(os.environ.get("TTS_SAY_RELAY_DAILY_CHARS", "20000"))
STATE_FILE = Path(os.environ.get("TTS_SAY_RELAY_STATE", "/tmp/tts-say-relay-usage.json"))
STATE_LOCK = threading.Lock()


def allowed_tokens() -> set[str]:
    raw = os.environ.get("TTS_SAY_RELAY_TOKENS", "")
    return {token.strip() for token in raw.split(",") if token.strip()}


def bearer_token(headers) -> str:
    value = headers.get("Authorization", "")
    if value.lower().startswith("bearer "):
        return value.split(" ", 1)[1].strip()
    return ""


def today_key() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))


def reserve_quota(token: str, chars: int) -> tuple[bool, int]:
    day = today_key()
    with STATE_LOCK:
        state = load_state()
        day_state = state.setdefault(day, {})
        used = int(day_state.get(token, 0))
        if used + chars > DAILY_CHARS:
            return False, max(0, DAILY_CHARS - used)
        day_state[token] = used + chars
        # Keep only today's counters.
        save_state({day: day_state})
        return True, DAILY_CHARS - day_state[token]


def synthesize(text: str) -> bytes:
    key = os.environ["MINIMAX_API_KEY"]
    body = {
        "model": MODEL,
        "text": text,
        "stream": False,
        "voice_setting": {"voice_id": VOICE_ID, "speed": 1.0, "vol": 1.0, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3"},
    }
    req = urllib.request.Request(
        "https://api.minimaxi.com/v1/t2a_v2",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
    if resp.get("base_resp", {}).get("status_code") != 0:
        raise RuntimeError(str(resp.get("base_resp")))
    return bytes.fromhex(resp["data"]["audio"])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def reply_json(self, code: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self.reply_json(200, {"ok": True})
        else:
            self.reply_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/say":
            self.reply_json(404, {"error": "not found"})
            return

        token = bearer_token(self.headers)
        tokens = allowed_tokens()
        if not tokens or token not in tokens:
            self.reply_json(401, {"error": "unauthorized"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            text = str(payload.get("text", "")).strip()
        except (ValueError, json.JSONDecodeError):
            self.reply_json(400, {"error": "bad json"})
            return

        if not text:
            self.reply_json(400, {"error": "empty text"})
            return
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + "。内容较长，后面就不读了。"

        ok, remaining = reserve_quota(token, len(text))
        if not ok:
            self.reply_json(429, {"error": "daily quota exceeded", "remaining_chars": remaining})
            return

        try:
            audio = synthesize(text)
        except Exception as exc:
            self.reply_json(502, {"error": "tts upstream failed", "detail": str(exc)})
            return

        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio)))
        self.send_header("X-Remaining-Chars", str(remaining))
        self.end_headers()
        self.wfile.write(audio)


def main():
    if not os.environ.get("MINIMAX_API_KEY"):
        raise SystemExit("MINIMAX_API_KEY is required")
    if not allowed_tokens():
        raise SystemExit("TTS_SAY_RELAY_TOKENS is required")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
