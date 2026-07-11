#!/usr/bin/env python3
"""tts_say.py — 把文本用 MiniMax TTS 合成并自动播放。

用法:
    python3 tts_say.py "要朗读的文本"
    echo "文本" | python3 tts_say.py
    python3 tts_say.py --no-interrupt "排队播放，不打断上一条"

行为:
    - 音色 female-tianmei (speech-02-hd)，密钥读 ~/.serenity_env
    - 清洗 markdown：代码块替换为"代码略"，去掉 URL、表格线、行内符号
    - 默认打断正在播放的上一条（聊天场景新回复优先）
    - 文本超过 MAX_CHARS 截断并追加提示
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
import base64
from pathlib import Path

MAX_CHARS = 3000
VOICE_ID = "female-tianmei"
MODEL = "speech-02-hd"
RUNTIME_DIR = Path(__file__).resolve().parent / ".runtime"
PID_FILE = RUNTIME_DIR / "afplay.pid"
ENV_FILE = Path.home() / ".serenity_env"


def load_env():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def load_key(required=True):
    load_env()
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if required and not key:
        raise RuntimeError(f"MINIMAX_API_KEY is missing. Add it to {ENV_FILE} or use macOS fallback.")
    return key


def choose_provider():
    load_env()
    provider = os.environ.get("TTS_SAY_PROVIDER", "auto").strip().lower() or "auto"
    relay_url = os.environ.get("TTS_SAY_RELAY_URL", "").strip()
    key = os.environ.get("MINIMAX_API_KEY", "").strip()

    if provider not in {"auto", "minimax", "relay", "macos"}:
        raise RuntimeError(f"Unsupported TTS_SAY_PROVIDER: {provider}")
    if provider == "auto":
        if key:
            return "minimax"
        if relay_url:
            return "relay"
        return "macos"
    return provider


def clean_text(text):
    # 代码块整块替换
    text = re.sub(r"```.*?```", "，代码略，", text, flags=re.S)
    text = re.sub(r"`[^`\n]+`", "", text)
    # URL
    text = re.sub(r"https?://\S+", "，链接略，", text)
    # markdown 标题/列表/引用/表格/加粗符号
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
    text = re.sub(r"^\s*\|.*\|\s*$", "", text, flags=re.M)  # 表格行
    text = re.sub(r"[*_#|]{1,3}", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # [文字](链接) -> 文字
    # 压缩空白
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "。内容较长，后面就不读了。"
    return text


def synthesize(text, key=None):
    provider = choose_provider()
    if provider == "minimax":
        return synthesize_minimax(text, key or load_key(required=True))
    if provider == "relay":
        return synthesize_relay(text)
    raise RuntimeError("macOS system voice does not synthesize mp3 bytes; call speak_text() instead.")


def synthesize_minimax(text, key):
    import urllib.request

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
        raise RuntimeError(f"TTS error: {resp.get('base_resp')}")
    return bytes.fromhex(resp["data"]["audio"])


def synthesize_relay(text):
    import urllib.request

    load_env()
    relay_url = os.environ.get("TTS_SAY_RELAY_URL", "").strip()
    if not relay_url:
        raise RuntimeError("TTS_SAY_RELAY_URL is missing for relay provider.")

    body = {
        "text": text,
        "model": MODEL,
        "voice_id": VOICE_ID,
    }
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("TTS_SAY_TRIAL_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(
        relay_url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        payload = response.read()
        content_type = response.headers.get("Content-Type", "")

    if content_type.startswith("audio/"):
        return payload

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Relay response was neither audio nor JSON.") from exc

    if data.get("audio_base64"):
        return base64.b64decode(data["audio_base64"])
    if data.get("audio_hex"):
        return bytes.fromhex(data["audio_hex"])
    if data.get("data", {}).get("audio"):
        return bytes.fromhex(data["data"]["audio"])
    raise RuntimeError(f"Relay response did not contain audio: {data.get('error') or data.keys()}")


def stop_previous():
    if PID_FILE.exists():
        try:
            os.kill(int(PID_FILE.read_text().strip()), signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass
        PID_FILE.unlink(missing_ok=True)


def wait_previous():
    while PID_FILE.exists():
        try:
            os.kill(int(PID_FILE.read_text().strip()), 0)
            time.sleep(0.5)
        except (ProcessLookupError, ValueError):
            PID_FILE.unlink(missing_ok=True)
            break


def play_audio_bytes(audio, interrupt=True):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    mp3 = RUNTIME_DIR / f"say_{int(time.time() * 1000)}.mp3"
    mp3.write_bytes(audio)

    if interrupt:
        stop_previous()
    else:
        wait_previous()

    proc = subprocess.Popen(["afplay", str(mp3)])
    PID_FILE.write_text(str(proc.pid))
    proc.wait()
    if PID_FILE.exists() and PID_FILE.read_text().strip() == str(proc.pid):
        PID_FILE.unlink(missing_ok=True)
    mp3.unlink(missing_ok=True)


def speak_macos(text, interrupt=True):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    txt = RUNTIME_DIR / f"say_{int(time.time() * 1000)}.txt"
    txt.write_text(text)

    if interrupt:
        stop_previous()
    else:
        wait_previous()

    command = ["say"]
    voice = os.environ.get("TTS_SAY_MACOS_VOICE", "").strip()
    if voice:
        command.extend(["-v", voice])
    command.extend(["-f", str(txt)])

    proc = subprocess.Popen(command)
    PID_FILE.write_text(str(proc.pid))
    proc.wait()
    if PID_FILE.exists() and PID_FILE.read_text().strip() == str(proc.pid):
        PID_FILE.unlink(missing_ok=True)
    txt.unlink(missing_ok=True)


def speak_text(text, interrupt=True):
    text = clean_text(text)
    if not text:
        return "empty"

    provider = choose_provider()
    if provider == "macos":
        speak_macos(text, interrupt=interrupt)
    else:
        play_audio_bytes(synthesize(text), interrupt=interrupt)
    cleanup_runtime()
    return provider


def cleanup_runtime():
    for old in RUNTIME_DIR.glob("say_*.mp3"):
        if time.time() - old.stat().st_mtime > 3600:
            old.unlink(missing_ok=True)
    for old in RUNTIME_DIR.glob("say_*.txt"):
        if time.time() - old.stat().st_mtime > 3600:
            old.unlink(missing_ok=True)


def main():
    args = sys.argv[1:]
    interrupt = True
    if "--no-interrupt" in args:
        interrupt = False
        args.remove("--no-interrupt")

    text = " ".join(args) if args else sys.stdin.read()
    text = clean_text(text)
    if not text:
        return
    speak_text(text, interrupt=interrupt)


if __name__ == "__main__":
    main()
