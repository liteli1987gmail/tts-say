// MiniMax 自动朗读 content script
// 轮询检测 AI 回复节点：文本停止增长 2.5 秒 = 回复完成 → 发给本地 TTS 服务。
// 页面已有的历史消息在初始化时标为已读，不会重播。

(() => {
  const POLL_MS = 1000;
  const STABLE_MS = 2500;

  // 各站点 assistant 消息节点的候选选择器（取第一个能匹配到的）
  const SITE_RULES = {
    "chatgpt.com": ['[data-message-author-role="assistant"]'],
    "chat.openai.com": ['[data-message-author-role="assistant"]'],
    "claude.ai": ['[data-is-streaming]', '.font-claude-message', '[data-testid="assistant-message"]'],
    "gemini.google.com": ["message-content", "model-response"],
    "chat.deepseek.com": [".ds-markdown"],
    "www.doubao.com": ['[data-testid="receive_message"]', '[class*="message-box"]'],
    "kimi.moonshot.cn": ['[class*="segment-assistant"]', ".markdown"],
    "www.kimi.com": ['[class*="segment-assistant"]', ".markdown"],
  };

  const candidates = SITE_RULES[location.hostname];
  if (!candidates) return;

  let enabled = true;
  chrome.storage.local.get("enabled").then(({ enabled: e = true }) => (enabled = e));
  chrome.storage.local.onChanged.addListener((ch) => {
    if (ch.enabled) enabled = ch.enabled.newValue;
  });

  let selector = null;
  const startedAt = Date.now();
  const seen = new WeakSet();          // 已朗读/已忽略的节点
  const watch = new Map();             // 节点 -> {len, since}

  function nodes() {
    if (!selector) {
      selector = candidates.find((s) => document.querySelector(s)) || null;
      if (!selector) return [];
      // 页面刚打开（3 秒内）就有消息 = 历史记录，标已读不重播；
      // 3 秒后才首次出现 = 新对话的第一条回复，应当朗读
      if (Date.now() - startedAt < 3000) {
        document.querySelectorAll(selector).forEach((n) => seen.add(n));
      }
      console.log("[MiniMax朗读] 使用选择器:", selector);
      return [];
    }
    return [...document.querySelectorAll(selector)];
  }

  function tick() {
    if (!enabled) return;
    const now = Date.now();
    for (const n of nodes()) {
      if (seen.has(n)) continue;
      const len = (n.innerText || "").trim().length;
      if (!len) continue;
      const w = watch.get(n);
      if (!w || w.len !== len) {
        watch.set(n, { len, since: now });
        continue;
      }
      if (now - w.since >= STABLE_MS) {
        seen.add(n);
        watch.delete(n);
        const text = n.innerText.trim();
        chrome.runtime.sendMessage(
          { type: "speak", text, source: location.hostname },
          (resp) => {
            if (!resp || !resp.ok)
              console.warn("[MiniMax朗读] 本地服务未响应，检查 tts_server 是否在跑", resp);
          }
        );
      }
    }
  }

  setInterval(tick, POLL_MS);
})();
