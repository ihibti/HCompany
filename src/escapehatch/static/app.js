/* Escape Hatch shared helpers */
window.EH = {
  fmtTime(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  },
  shotSrc(url) {
    if (!url) return null;
    if (url.startsWith("/")) return url;
    return "/api/shot?u=" + encodeURIComponent(url);
  },
  hostOf(url) {
    try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url || ""; }
  },
  taskLabel(t) {
    return (t || "").replace(/_/g, " ");
  },
};
