#!/usr/bin/env python3
"""Minimal stdio MCP server for tts-say.

It intentionally avoids third-party dependencies so users can expose tts-say to
their own LLM client immediately after cloning this repository.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import tts_say_status

SERVER_NAME = "tts-say"
SERVER_VERSION = "0.1.0"


def shell(command: list[str], timeout: int = 180) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=PROJECT_DIR,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "command": command,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
            "command": command,
        }


def text_result(data: Any, is_error: bool = False) -> dict[str, Any]:
    if isinstance(data, str):
        text = data
    else:
        text = json.dumps(data, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def read_json_line() -> dict[str, Any] | None:
    line = sys.stdin.readline()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"jsonrpc": "2.0", "id": None, "method": "$invalid", "params": {"line": line}}


def write_message(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


TOOLS: list[dict[str, Any]] = [
    {
        "name": "doctor",
        "description": "Return structured diagnostics for tts-say without exposing secrets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_logs": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "install",
        "description": "Run the macOS installer. Defaults avoid test audio; Chrome extension automation is optional.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "test_audio": {"type": "boolean", "default": False},
                "chrome_extension": {"type": "boolean", "default": True},
                "hooks": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "install_chrome_extension",
        "description": "Try to load the unpacked Chrome extension through Chrome UI automation.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "uninstall",
        "description": "Uninstall service and hooks. Removing the MiniMax key is opt-in.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "remove_key": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "start_service",
        "description": "Start or restart the LaunchAgent service when the plist already exists.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "stop_service",
        "description": "Stop the LaunchAgent service and any current afplay process.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "play_test_audio",
        "description": "Synthesize and play a short test sentence through MiniMax and afplay.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "default": "tts-say test audio.",
                    "description": "Text to speak. Keep it short.",
                },
            },
        },
    },
    {
        "name": "get_logs",
        "description": "Return recent tts-say server logs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lines": {"type": "integer", "default": 80, "minimum": 1, "maximum": 500},
            },
        },
    },
]


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    arguments = arguments or {}

    if name == "doctor":
        return text_result(tts_say_status.collect_status(include_logs=bool(arguments.get("include_logs", False))))

    if name == "install":
        command = [str(PROJECT_DIR / "install.sh")]
        if not bool(arguments.get("test_audio", False)):
            command.append("--no-test-audio")
        if not bool(arguments.get("chrome_extension", True)):
            command.append("--no-chrome-ext")
        if not bool(arguments.get("hooks", True)):
            command.append("--no-hooks")
        result = shell(command, timeout=600)
        result["status"] = tts_say_status.collect_status(include_logs=False)
        return text_result(result, is_error=not result["ok"])

    if name == "install_chrome_extension":
        result = shell([str(PROJECT_DIR / "install_chrome_ext.sh")], timeout=120)
        result["status"] = tts_say_status.collect_status(include_logs=False)
        return text_result(result, is_error=not result["ok"])

    if name == "uninstall":
        command = [str(PROJECT_DIR / "uninstall.sh")]
        if bool(arguments.get("remove_key", False)):
            command.append("--remove-key")
        result = shell(command, timeout=300)
        result["status"] = tts_say_status.collect_status(include_logs=False)
        return text_result(result, is_error=not result["ok"])

    if name == "start_service":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.terri.tts-say.plist"
        if not plist.exists():
            return text_result({"ok": False, "error": f"LaunchAgent plist missing: {plist}"}, is_error=True)
        commands = [
            ["launchctl", "bootout", f"gui/{os.getuid()}", str(plist)],
            ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)],
            ["launchctl", "enable", f"gui/{os.getuid()}/com.terri.tts-say"],
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.terri.tts-say"],
        ]
        results = []
        for index, command in enumerate(commands):
            result = shell(command, timeout=30)
            if index == 0:
                result["ignored"] = True
            results.append(result)
        return text_result({"ok": tts_say_status.collect_status()["service"]["responds"], "results": results})

    if name == "stop_service":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.terri.tts-say.plist"
        results = [shell(["launchctl", "bootout", f"gui/{os.getuid()}", str(plist)], timeout=30)]
        pid_file = PROJECT_DIR / ".runtime" / "afplay.pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 15)
                pid_file.unlink(missing_ok=True)
                results.append({"ok": True, "action": "stopped_afplay", "pid": pid})
            except (OSError, ValueError) as exc:
                results.append({"ok": False, "action": "stopped_afplay", "error": str(exc)})
        return text_result({"ok": True, "results": results})

    if name == "play_test_audio":
        text = str(arguments.get("text") or "tts-say test audio.")[:500]
        result = shell(["python3", str(PROJECT_DIR / "tts_say.py"), text], timeout=180)
        return text_result(result, is_error=not result["ok"])

    if name == "get_logs":
        lines = int(arguments.get("lines") or 80)
        lines = max(1, min(500, lines))
        logs = {
            "server_err": tts_say_status.tail(PROJECT_DIR / ".runtime" / "server.err.log", lines),
            "server_out": tts_say_status.tail(PROJECT_DIR / ".runtime" / "server.out.log", lines),
        }
        return text_result(logs)

    return text_result({"ok": False, "error": f"Unknown tool: {name}"}, is_error=True)


def handle(request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if request_id is None and method != "$invalid":
        return None

    if method == "$invalid":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32700, "message": "Parse error"},
        }

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            result = call_tool(str(name), arguments)
        except Exception as exc:  # Keep MCP server alive on tool bugs.
            result = text_result({"ok": False, "error": str(exc)}, is_error=True)
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:
    while True:
        request = read_json_line()
        if request is None:
            return 0
        response = handle(request)
        if response is not None:
            write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())
