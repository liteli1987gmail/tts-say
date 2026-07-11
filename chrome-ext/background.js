// 后台转发：content script 抓到的回复文本 → 本地 tts_server
// 从 service worker 发 fetch，不受页面 CSP 限制。

const SERVER = "http://127.0.0.1:48765/say";

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type !== "speak") return;
  fetch(SERVER, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: msg.text, source: msg.source || "" }),
  })
    .then((r) => sendResponse({ ok: r.ok }))
    .catch((e) => sendResponse({ ok: false, error: String(e) }));
  return true; // 异步 sendResponse
});

// 点扩展图标切换开/关，角标显示状态
async function refreshBadge() {
  const { enabled = true } = await chrome.storage.local.get("enabled");
  chrome.action.setBadgeText({ text: enabled ? "开" : "关" });
  chrome.action.setBadgeBackgroundColor({ color: enabled ? "#34a853" : "#9aa0a6" });
}

chrome.action.onClicked.addListener(async () => {
  const { enabled = true } = await chrome.storage.local.get("enabled");
  await chrome.storage.local.set({ enabled: !enabled });
  refreshBadge();
});

chrome.runtime.onInstalled.addListener(refreshBadge);
chrome.runtime.onStartup.addListener(refreshBadge);
