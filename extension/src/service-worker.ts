chrome.runtime.onMessageExternal.addListener((msg, sender, sendResponse) => {
  if (msg?.type === "ping") sendResponse({ ok: true });
  return false;
});
export { };