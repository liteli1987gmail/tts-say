# tts-say

[English](README.md)

tts-say 让 AI 回复自动用语音朗读出来，把阅读 AI 回复的工作流扩展为可听的体验。

它支持三条入口：

- Claude Code Stop hook
- Codex notify hook
- Chrome 扩展监听 ChatGPT、Claude、Gemini、DeepSeek、豆包、Kimi 等网页

默认 TTS 厂商是 MiniMax。首次体验可使用 macOS `say` 系统语音；产品试用可通过私有 relay 使用 MiniMax 音色。

## 安装

```sh
git clone https://github.com/liteli1987gmail/tts-say.git
cd tts-say
cp .env.example .env
./install.sh
```

打开 `.env`，填入你自己的 `MINIMAX_API_KEY` 即可使用 MiniMax 音色。首次体验可以先留空，使用 macOS 系统语音。

安装器会完成：

- 检查 macOS、Python、`afplay`、`say`、`curl`
- 从 `.env.example` 创建 `.env`
- 检查 `.env` 里的 `MINIMAX_API_KEY`
- 在 first-run demo 场景使用 macOS `say` 系统语音
- 安装并启动 `~/Library/LaunchAgents/com.terri.tts-say.plist`
- 验证 `http://127.0.0.1:48765/ping`
- 配置 Claude Code Stop hook
- 配置 Codex notify hook，并保留已有 notify
- 播放一句测试语音
- 在本机安装 Google Chrome 时，打开扩展页面、开启 Developer mode，并选择本地 `chrome-ext` 目录

Chrome 本地解压扩展通过 `chrome://extensions/` 加载。`install.sh` 会使用 macOS UI 自动化完成这一步；遇到系统辅助功能权限或页面结构差异时，可以按下面步骤加载：

1. 打开 `chrome://extensions/`
2. 开启 Developer mode
3. 点击 Load unpacked
4. 选择 `chrome-ext` 文件夹

单独重试浏览器扩展安装：

```sh
./install_chrome_ext.sh
```

如果 macOS 提示辅助功能权限，请在 System Settings 里允许当前终端 App 控制电脑，然后重新运行上面的命令。

## 常用命令

```sh
./doctor.sh
```

检查服务、配置、Chrome 扩展文件、TTS provider 和 MiniMax key。Chrome 已加载本地扩展时，诊断里会显示 Chrome profile 和 extension id。

```sh
./doctor.sh --json --pretty
```

输出给 LLM/MCP 读取的结构化诊断结果，结果只显示 key 是否存在。

```sh
./uninstall.sh
```

卸载 LaunchAgent，并移除 Claude/Codex hook。Chrome 扩展可在 `chrome://extensions/` 里移除。

```sh
./install.sh --no-test-audio
./install.sh --no-open-browser
./install.sh --no-chrome-ext
```

这些选项分别用于跳过测试语音、跳过 Chrome 页面操作、跳过 Chrome 扩展安装。

## 手动使用

```sh
python3 tts_say.py "你好，我会朗读这句话。"
echo "从标准输入读文本" | python3 tts_say.py
python3 tts_say.py --no-interrupt "排队播放，等上一条播完。"
```

TTS provider 选择顺序：

1. `MINIMAX_API_KEY` 存在时使用 MiniMax。
2. `TTS_SAY_RELAY_URL` 存在时使用试用 relay，可配合 `TTS_SAY_TRIAL_TOKEN`。
3. 首次体验场景使用 macOS `say` 系统语音。

强制指定 provider：

```sh
TTS_SAY_PROVIDER=macos python3 tts_say.py "Use the built-in macOS voice."
TTS_SAY_PROVIDER=relay python3 tts_say.py "Use my trial relay."
TTS_SAY_PROVIDER=minimax python3 tts_say.py "Require MiniMax."
```

默认厂商是 MiniMax。其他 AI agent 扩展 TTS 厂商时，优先阅读 [docs/PROVIDERS.md](docs/PROVIDERS.md)。provider 逻辑集中在 `tts_say.py` 和诊断文档，Chrome 扩展、Claude hook、Codex hook 只负责把文本送到本地 TTS 层。

本地服务：

```sh
curl http://127.0.0.1:48765/ping
curl -X POST http://127.0.0.1:48765/say \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello from tts-say"}'
```

## 文件结构

- `tts_say.py`: 文本清洗、provider 选择、MiniMax/relay/macOS 语音播放
- `tts_server.py`: 本地 HTTP 服务，供浏览器扩展调用
- `tts_say_status.py`: 结构化诊断，供 `doctor.sh --json` 和 MCP 复用
- `claude_stop_hook.py`: Claude Code 回复结束后朗读最后一条 assistant 消息
- `codex_notify_tts.py`: Codex 回合结束后朗读最后一条 assistant 消息
- `codex_notify_wrapper.sh`: Codex notify 包装器，可保留原 notify
- `chrome-ext/`: Chrome MV3 扩展
- `install.sh`: 一键安装
- `install_chrome_ext.sh`: 通过 Chrome UI 自动加载本地扩展
- `doctor.sh`: 诊断
- `uninstall.sh`: 卸载
- `mcp/tts_say_mcp.py`: 给 LLM 客户端调用的 stdio MCP server
- `skills/tts-say-installer/`: 给 Codex/LLM 阅读的安装与修复 skill
- `relay/minimax_relay.py`: 私有试用 relay 示例，服务端持有 MiniMax key
- `docs/TRIAL_RELAY.md`: trial token 试用 MiniMax 音色的部署说明
- `docs/PROVIDERS.md`: provider 扩展说明

## 配置和试用

安装器会在修改现有配置前生成带时间戳的备份：

- `~/.claude/settings.json.tts-say.bak-YYYYMMDD-HHMMSS`
- `~/.codex/config.toml.tts-say.bak-YYYYMMDD-HHMMSS`
- `~/Library/LaunchAgents/com.terri.tts-say.plist.tts-say.bak-YYYYMMDD-HHMMSS`

用户体验 MiniMax 音色的推荐方式是 trial relay：

```text
用户机器 -> tts-say local client -> 你的 relay -> MiniMax
```

用户本地只保存：

```sh
cp .env.example .env
TTS_SAY_RELAY_URL=https://your-domain.example/say
TTS_SAY_TRIAL_TOKEN=demo-user-token
```

真实 `MINIMAX_API_KEY` 保存在你的服务器环境变量里。详见 [docs/TRIAL_RELAY.md](docs/TRIAL_RELAY.md)。

## 给 LLM 客户端使用

这个项目提供 skill 和 MCP 两种 AI 接入方式。

Skill 位于：

```text
skills/tts-say-installer
```

支持 Codex skill 的客户端可以把这个目录复制或链接到自己的 skills 目录。这个 skill 会指导 LLM 定位项目、运行诊断、安装服务、配置 Claude/Codex hooks、加载 Chrome 扩展，以及安全处理 MiniMax key。

MCP server 位于：

```text
mcp/tts_say_mcp.py
```

典型 stdio 配置：

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

MCP 工具包括：

- `doctor`
- `install`
- `install_chrome_extension`
- `uninstall`
- `start_service`
- `stop_service`
- `play_test_audio`
- `get_logs`

建议让 LLM 先调用 `doctor`，再根据结构化状态选择最小修复动作。
