#!/usr/bin/env python3
"""Claude Code Stop hook — 回复结束后自动朗读最后一条 assistant 消息。

stdin 收 hook JSON（含 transcript_path），提取最后一条 assistant 的文本，
派生后台进程调 tts_say.py，立即返回不阻塞会话。
"""
import json
import subprocess
import sys
from pathlib import Path

TTS = Path(__file__).resolve().parent / "tts_say.py"


def last_assistant_text(transcript_path):
    text = None
    try:
        with open(transcript_path) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != "assistant":
                    continue
                content = entry.get("message", {}).get("content", [])
                parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                if any(p.strip() for p in parts):
                    text = "\n".join(parts)
    except OSError:
        pass
    return text


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    # stop_hook_active 为真说明是 hook 触发的续跑，避免循环
    if payload.get("stop_hook_active"):
        return
    text = last_assistant_text(payload.get("transcript_path", ""))
    if not text:
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
