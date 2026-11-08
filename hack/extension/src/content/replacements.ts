// In-flow replacement card for a tomatoed tile.
import type { VideoMeta } from "../shared/api";

export interface Replacement {
  platform: string; id: string; url: string; title: string; channel: string;
  thumbnail_url: string; kind: string; reason: string; source: string;
  duration?: string; views?: string;
}

/** YouTube's own theme wins over the OS setting (html[dark] is set by YouTube). */
export function pageIsDark(): boolean {
  if (location.hostname.includes("youtube.com")) return document.documentElement.hasAttribute("dark");
  return matchMedia("(prefers-color-scheme: dark)").matches;
}

const CSS = `
:host { all: initial; display: block; }
.rc { display: block; text-decoration: none; background: var(--rc-bg, transparent); border-radius: 8px; overflow: hidden;
  font: 500 14px/1.35 "Roboto", "Segoe UI", Arial, sans-serif; color: var(--rc-fg, #0f0f0f); cursor: pointer;
  transition: transform .16s ease-out, box-shadow .16s ease-out; }
.rc:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(0,0,0,.18); }
.thumb { position: relative; width: 100%; aspect-ratio: 16/9; background: #e2ddd5; }
.thumb.short { aspect-ratio: 9/16; }
.thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.thumb .dur { position: absolute; right: 6px; bottom: 6px; background: rgba(0,0,0,.8); color: #fff; font-size: 12px; font-weight: 600; border-radius: 4px; padding: 1px 4px; }
.thumb .ph { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; }
.meta { padding: 8px 4px 4px; }
.t { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-weight: 600; }
.c { color: var(--rc-mut, #606060); font-size: 12.5px; margin-top: 2px; }
.tag { display: inline-flex; align-items: center; gap: 5px; margin-top: 6px; font-size: 11.5px;
  color: oklch(0.5 0.16 38); background: oklch(0.94 0.04 40); border-radius: 999px; padding: 2px 8px; }
.tag .undo { font-weight: 700; color: #c0392b; margin-left: 6px; }
.shelf .tag { display: flex; max-width: 100%; box-sizing: border-box; }
.shelf .tag span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
`;

export class ReplacementCard {
  host: HTMLElement;
  onUndo?: () => void;
  onTomato?: () => void;

  constructor(rep: Replacement, rect: DOMRect | null, isDark: boolean, variant: "tile" | "shelf" = "tile") {
    this.host = document.createElement("div");
    this.host.className = "tomate-replacement";
    if (rect) {
      this.host.style.minHeight = `${rect.height}px`;
      this.host.style.width = `${rect.width}px`;
    }
    const sh = this.host.attachShadow({ mode: "open" });
    const st = document.createElement("style");
    st.textContent = CSS + (isDark
      ? `:host .rc{ --rc-fg:#f1f1f1; --rc-mut:#aaa }`
      : `:host .rc{ --rc-fg:#0f0f0f; --rc-mut:#606060 }`);
    sh.appendChild(st);
    const short = rep.kind === "short" || rep.platform !== "youtube";
    const div = document.createElement("a");
    div.className = "rc" + (variant === "shelf" ? " shelf" : "");
    div.href = rep.url;
    div.innerHTML = `
      <div class="thumb ${short ? "short" : ""}">
        ${rep.thumbnail_url ? `<img src="${esc(rep.thumbnail_url)}" alt="">` :
          `<div class="ph">${TOMATO_ICON(28)}</div>`}
        ${rep.duration ? `<span class="dur">${esc(rep.duration)}</span>` : ""}
      </div>
      <div class="meta">
        <div class="t">${esc(rep.title)}</div>
        <div class="c">${esc([rep.channel, rep.views].filter(Boolean).join(" · "))}</div>
        ${variant === "shelf"
          ? `<div class="tag" title="${esc(rep.reason || "")}">${TOMATO_ICON(12)}<span>${esc(rep.reason || "dans le sujet")}</span></div>`
          : `<div class="tag">${TOMATO_ICON(12)}<span>Proposé par Tomate${rep.reason ? ` · ${esc(rep.reason)}` : ""}</span><span class="undo">Pardon ?</span></div>`}
      </div>`;
    sh.appendChild(div);
    div.querySelector(".undo")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.onUndo?.();
    });
  }

  mountAfter(el: Element) {
    el.parentElement?.insertBefore(this.host, el.nextSibling);
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
      this.host.animate(
        [{ transform: "scale(.9)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }],
        { duration: 300, easing: "cubic-bezier(.2,.7,.3,1)" });
    } else {
      this.host.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 250 });
    }
  }

  remove() { this.host.remove(); }
}

function esc(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}

export function TOMATO_ICON(sz: number) {
  return `<svg width="${sz}" height="${sz}" viewBox="0 0 26 26" xmlns="http://www.w3.org/2000/svg"><circle cx="13" cy="14" r="10" fill="#d63031"/><path d="M13 4c-2 2-5 2-6 1 2-2 4-3 6-1zm0 0c2 2 5 2 6 1-2-2-4-3-6-1z" stroke="#27ae60" stroke-width="2" fill="none" stroke-linecap="round"/></svg>`;
}
