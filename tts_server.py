#!/usr/bin/env python3
"""tts_server.py — 本地 TTS HTTP 服务，供浏览器扩展等调用。

POST http://127.0.0.1:48765/say   body: {"text": "...", "source": "chatgpt.com"}
GET  http://127.0.0.1:48765/ping  -> ok

- 复用 tts_say.py 的清洗/合成/播放逻辑
- 按文本 hash 去重（最近 200 条），同一条回复不会重复播
- 合成播放在后台线程排队，新回复打断上一条
"""
import hashlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tts_say

PORT = 48765
recent = []          # 最近播过的文本 hash
recent_lock = threading.Lock()


def speak(text):
    try:
        tts_say.speak_text(text, interrupt=True)
    except Exception as e:
        sys.stderr.write(f"speak failed: {e}\n")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/ping":
            self._reply(200, {"ok": True})
        else:
            self._reply(404, {"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path != "/say":
            self._reply(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            text = (payload.get("text") or "").strip()
        except (ValueError, json.JSONDecodeError):
            self._reply(400, {"error": "bad json"})
            return
        if not text:
            self._reply(400, {"error": "empty text"})
            return

        digest = hashlib.sha256(text.encode()).hexdigest()
        with recent_lock:
            if digest in recent:
                self._reply(200, {"ok": True, "deduped": True})
                return
            recent.append(digest)
            del recent[:-200]

        threading.Thread(target=speak, args=(text,), daemon=True).start()
        self._reply(200, {"ok": True})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
