#!/usr/bin/env python3
"""Codex CLI notify 钩子 — agent 回合结束后自动朗读最后一条回复。

Codex 在 ~/.codex/config.toml 的 notify 配置下，回合结束时以
argv[1] = JSON 调用本脚本，JSON 含 type 和 last-assistant-message。
"""
import json
import subprocess
import sys
from pathlib import Path

TTS = Path(__file__).resolve().parent / "tts_say.py"


def main():
    if len(sys.argv) < 2:
        return
    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        return
    if payload.get("type") != "agent-turn-complete":
        return
    text = payload.get("last-assistant-message") or ""
    if not text.strip():
        return
    proc = subprocess.Popen(
        ["python3", str(TTS)],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    proc.stdin.write(text.encode())
    proc.stdin.close()


if __name__ == "__main__":
    main()
