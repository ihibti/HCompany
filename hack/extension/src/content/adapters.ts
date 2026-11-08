import type { VideoMeta } from "../shared/api";

export interface Adapter {
  platform: string;
  matches(host: string): boolean;
  findCards(root: ParentNode): Element[];
  extract(card: Element): VideoMeta | null;
}

const text = (el: Element | null | undefined) => (el?.textContent ?? "").trim();

function hrefId(href: string): string | null {
  const m = href.match(/[?&]v=([\w-]+)/) ?? href.match(/\/shorts\/([\w-]+)/)
    ?? href.match(/\/video\/(\d+)/) ?? href.match(/\/reel\/([\w-]+)/)
    ?? href.match(/\/p\/([\w-]+)/);
  return m?.[1] ?? null;
}

function abs(href: string): string {
  try { return new URL(href, location.origin).href; } catch { return href; }
}

function hashtagsOf(t: string): string[] {
  return [...t.matchAll(/#([\wàâäéèêëîïôöùûüç-]+)/gi)].map((m) => m[1]).slice(0, 10);
}

function cardFromAnchor(a: Element, maxUp = 6): Element {
  let el: Element = a;
  for (let i = 0; i < maxUp && el.parentElement; i++) {
    el = el.parentElement;
    const r = el.getBoundingClientRect();
    if (r.height > 120 && r.height < 800 && el.children.length > 1) return el;
  }
  return a.parentElement ?? a;
}

export const youtube: Adapter = {
  platform: "youtube",
  matches: (h) => h.includes("youtube.com") || h === "localhost",
  findCards: (root) => Array.from(root.querySelectorAll(
    "ytd-rich-item-renderer, ytd-video-renderer, ytd-compact-video-renderer, ytd-reel-item-renderer, ytm-shorts-lockup-view-model, ytm-shorts-lockup-view-model-v2, yt-lockup-view-model, grid-shelf-view-model, .fx-card[data-platform='youtube']"))
    .filter((el) => !el.closest("ytd-ad-slot-renderer, ytd-display-ad-renderer, ytd-in-feed-ad-layout-renderer, [data-ad-slot-id], ytd-promoted-sparkles-web-renderer")),
  extract: (card) => {
    const a = card.querySelector("a#video-title-link, a#thumbnail, a[href*='watch?v='], a[href*='/shorts/']") as HTMLAnchorElement | null;
    if (!a?.href) return null;
    const id = hrefId(a.href);
    if (!id) return null;
    const title = text(card.querySelector("#video-title, #video-title-link, .title, h3, h4")) || a.title || a.getAttribute("aria-label") || "";
    const channel = text(card.querySelector("ytd-channel-name, #channel-name, .ytd-channel-name, [data-e2e='channel']"));
    const desc = text(card.querySelector("#description-text, .description"));
    return { platform: "youtube", id, url: abs(a.href), title, channel, description: desc, hashtags: hashtagsOf(title + " " + desc) };
  },
};

export const tiktok: Adapter = {
  platform: "tiktok",
  matches: (h) => h.includes("tiktok.com") || h === "localhost",
  findCards: (root) => Array.from(root.querySelectorAll(
    "[data-e2e='recommend-list-item-container'], [data-e2e='explore-item'], .fx-card[data-platform='tiktok']")),
  extract: (card) => {
    const a = card.querySelector("a[href*='/video/']") as HTMLAnchorElement | null;
    const id = a ? hrefId(a.href) : card.getAttribute("data-video-id");
    if (!id) return null;
    const caption = text(card.querySelector("[data-e2e*='desc'], [class*='DescSpan'], .caption"));
    const author = text(card.querySelector("[data-e2e*='author'], [data-e2e*='name'], .author"));
    return { platform: "tiktok", id, url: a ? abs(a.href) : location.href,
             title: caption || author, channel: author, description: caption,
             hashtags: hashtagsOf(caption) };
  },
};

export const instagram: Adapter = {
  platform: "instagram",
  matches: (h) => h.includes("instagram.com") || h === "localhost",
  findCards: (root) => Array.from(root.querySelectorAll(
    "article, [role='presentation'] a[href^='/reel/'], .fx-card[data-platform='instagram']"))
    .map((el) => (el.tagName === "A" ? cardFromAnchor(el) : el)),
  extract: (card) => {
    const a = card.querySelector("a[href*='/reel/'], a[href*='/p/']") as HTMLAnchorElement | null;
    const id = a ? hrefId(a.href) : null;
    if (!id) return null;
    const caption = text(card.querySelector("h1, [class*='Caption'], .caption"));
    const author = text(card.querySelector("header a, .author"));
    return { platform: "instagram", id, url: a ? abs(a.href) : location.href,
             title: caption || author, channel: author, description: caption,
             hashtags: hashtagsOf(caption) };
  },
};

const generic: Adapter = {
  platform: "generic",
  matches: () => true,
  findCards: (root) => {
    const anchors = Array.from(root.querySelectorAll(
      "a[href*='watch?v='], a[href*='/shorts/'], a[href*='/video/'], a[href*='/reel/'], a[href*='/p/']"));
    const seen = new Set<Element>();
    const out: Element[] = [];
    for (const a of anchors) {
      const c = cardFromAnchor(a);
      if (!seen.has(c)) { seen.add(c); out.push(c); }
    }
    return out;
  },
  extract: (card) => {
    const a = card.querySelector("a[href*='watch?v='], a[href*='/shorts/'], a[href*='/video/'], a[href*='/reel/'], a[href*='/p/']") as HTMLAnchorElement | null;
    const id = a ? hrefId(a.href) : null;
    if (!a || !id) return null;
    return { platform: "generic", id, url: abs(a.href), title: text(a) || a.title,
             channel: "", description: text(card).slice(0, 300), hashtags: hashtagsOf(text(card)) };
  },
};

export const ADAPTERS: Adapter[] = [youtube, tiktok, instagram, generic];

export function pickAdapter(host: string): Adapter {
  if (host.includes("youtube.com")) return youtube;
  if (host.includes("tiktok.com")) return tiktok;
  if (host.includes("instagram.com")) return instagram;
  // fixtures: platform indicated by the path's first segment or data attr
  const seg = (location.pathname.split("/")[1] ?? "").replace(".html", "");
  const fx = ADAPTERS.find((a) => a.platform === seg);
  return fx ?? generic;
}
