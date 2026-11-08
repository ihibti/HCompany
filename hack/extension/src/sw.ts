// Service worker: backend fetch relay (avoids page CORS/CSP), badge, context menu.

const DEFAULT_BACKEND = "http://localhost:8787";

async function backendUrl(): Promise<string> {
  const { backendUrl } = await chrome.storage.local.get("backendUrl");
  return (backendUrl as string) || DEFAULT_BACKEND;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.kind === "fetch") {
    (async () => {
      try {
        const base = await backendUrl();
        const r = await fetch(base + msg.path, {
          method: msg.method ?? "GET",
          headers: msg.body !== undefined ? { "Content-Type": "application/json" } : undefined,
          body: msg.body !== undefined ? JSON.stringify(msg.body) : undefined,
        });
        const data = r.status === 204 ? null : await r.json().catch(() => null);
        sendResponse({ ok: r.ok, status: r.status, data, error: r.ok ? undefined : JSON.stringify(data) });
      } catch (e) {
        sendResponse({ ok: false, status: 0, error: String(e) });
      }
    })();
    return true; // async response
  }
  if (msg?.kind === "badge" && sender.tab?.id != null) {
    const n = msg.count as number;
    chrome.action.setBadgeText({ tabId: sender.tab.id, text: n > 0 ? String(n) : "" });
    chrome.action.setBadgeBackgroundColor({ tabId: sender.tab.id, color: "#c0392b" });
  }
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "tomate-throw",
    title: "Lancer une tomate",
    contexts: ["link"],
    targetUrlPatterns: [
      "*://*.youtube.com/*", "*://*.tiktok.com/*", "*://*.instagram.com/*",
      "http://localhost:8899/*",
    ],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "tomate-throw" && tab?.id) {
    chrome.tabs.sendMessage(tab.id, { kind: "userThrow" });
  }
});

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg?.kind === "openPanel" && sender.tab?.id != null) {
    chrome.sidePanel.open({ tabId: sender.tab.id }).catch(() => {});
  }
});

chrome.action.onClicked.addListener((tab) => {
  if (tab.id) chrome.sidePanel.open({ tabId: tab.id });
});
