// YouTube in-page search pool — same-origin /results?search_query= parsing.
import type { Replacement } from "./replacements";

export interface YtVideo { id: string; title: string; channel: string; thumbnail_url: string; duration?: string; views?: string; kind: "video" | "short" }

export interface TopicSpec { topic: string; keywords?: string[]; example_creators?: string[] }

function* walk(node: unknown): Generator<Record<string, any>> {
  if (Array.isArray(node)) { for (const n of node) yield* walk(n); return; }
  if (node && typeof node === "object") { yield node as Record<string, any>; for (const v of Object.values(node)) yield* walk(v); }
}

export function parseYtInitialData(html: string): YtVideo[] {
  const m = html.match(/var ytInitialData = (\{.+?\});<\/script>/s) ?? html.match(/ytInitialData"?\s*=\s*(\{.+?\});/s);
  if (!m) return [];
  let data: unknown;
  try { data = JSON.parse(m[1]); } catch { return []; }
  const out = new Map<string, YtVideo>();
  for (const n of walk(data)) {
    const vr = n.videoRenderer;
    if (vr?.videoId && !out.has(vr.videoId)) {
      const title = (vr.title?.runs?.[0]?.text ?? vr.title?.simpleText ?? "").trim();
      const channel = (vr.ownerText?.runs?.[0]?.text ?? vr.longBylineText?.runs?.[0]?.text ?? "").trim();
      const thumb = vr.thumbnail?.thumbnails?.at(-1)?.url ?? "";
      out.set(vr.videoId, { id: vr.videoId, title, channel, thumbnail_url: thumb || `https://i.ytimg.com/vi/${vr.videoId}/hqdefault.jpg`,
        duration: vr.lengthText?.simpleText, views: vr.viewCountText?.simpleText, kind: "video" });
      continue;
    }
    // new lockupViewModel shape
    const lv = n.lockupViewModel;
    if (lv) {
      const cmd = lv.rendererContext?.commandContext?.onTap?.innertubeCommand;
      const id = lv.videoId ?? cmd?.watchEndpoint?.videoId ?? cmd?.reelWatchEndpoint?.videoId ?? lv.contentId;
      const isVideo = !lv.contentType || /VIDEO|SHORT/.test(String(lv.contentType));
      if (id && typeof id === "string" && isVideo && !out.has(id)) {
        const md = lv.metadata?.lockupMetadataViewModel;
        const title = md?.title?.content?.trim?.() ?? "";
        const channel = md?.metadata?.contentMetadataViewModel?.metadataRows?.flatMap?.((r: any) => r.metadataParts ?? [])?.[0]?.text?.content?.trim?.() ?? "";
        const thumb = lv.contentImage?.thumbnailViewModel?.image?.sources?.at(-1)?.url ?? "";
        const isShort = String(lv.contentType ?? "").includes("SHORT") || !!cmd?.reelWatchEndpoint;
        out.set(id, { id, title, channel, kind: isShort ? "short" : "video",
          thumbnail_url: thumb || `https://i.ytimg.com/vi/${id}/${isShort ? "oar2" : "hqdefault"}.jpg` });
      }
      continue;
    }
    // shorts lockup (search shelves): no channel name, secondaryText is the view count
    const sl = n.shortsLockupViewModel;
    if (sl?.entityId || sl?.videoId) {
      const reel = sl.onTap?.innertubeCommand?.reelWatchEndpoint;
      const id = sl.videoId ?? reel?.videoId ?? String(sl.entityId).match(/shorts-shelf-item-([\w-]+)/)?.[1];
      if (id && !out.has(id)) {
        out.set(id, { id, title: (sl.overlayMetadata?.primaryText?.content ?? "").trim(), channel: "",
          views: sl.overlayMetadata?.secondaryText?.content,
          thumbnail_url: sl.thumbnail?.sources?.at(-1)?.url ?? reel?.thumbnail?.thumbnails?.at(-1)?.url ?? `https://i.ytimg.com/vi/${id}/oar2.jpg`,
          kind: "short" });
      }
    }
  }
  return [...out.values()];
}

// Shared by the feed shelf and the replacement buffer so both don't re-download the same 1-2 MB result pages.
const searchCache = new Map<string, { at: number; p: Promise<YtVideo[]> }>();
const SEARCH_TTL = 10 * 60_000;

export async function ytSearch(query: string, shortsOnly = false): Promise<YtVideo[]> {
  let hit = searchCache.get(query);
  if (!hit || Date.now() - hit.at > SEARCH_TTL) {
    const p = (async () => {
      const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;
      const resp = await fetch(url, { credentials: "include" });
      if (!resp.ok) return [];
      return parseYtInitialData(await resp.text());
    })();
    hit = { at: Date.now(), p };
    searchCache.set(query, hit);
    p.catch(() => searchCache.delete(query));
  }
  const vids = await hit.p;
  return shortsOnly ? vids.filter(v => v.kind === "short") : vids;
}

/** Search queries for one "round". Each round rotates through keywords/creators so a refresh brings new videos. */
export function feedQueries(include: TopicSpec[], round: number): string[] {
  const out: string[] = [];
  for (const t of include) {
    const kw = (t.keywords ?? []).filter(Boolean);
    const cr = (t.example_creators ?? []).filter(Boolean);
    const picks = kw.length || cr.length
      ? [kw.length ? kw[(round * 2) % kw.length] : "", cr.length ? cr[round % cr.length] : "", kw.length > 1 ? kw[(round * 2 + 1) % kw.length] : ""]
      : [t.topic];
    for (const q of picks) if (q && !out.includes(q)) out.push(q);
  }
  return out;
}

/** Round-robin merge so every query (hence every topic) is represented near the top. */
export function interleave<T>(lists: T[][]): T[] {
  const out: T[] = [];
  const max = Math.max(0, ...lists.map(l => l.length));
  for (let i = 0; i < max; i++) for (const l of lists) if (i < l.length) out.push(l[i]);
  return out;
}

export function toReplacement(v: YtVideo, reason: string): Replacement {
  return { platform: "youtube", id: v.id,
    url: v.kind === "short" ? `https://www.youtube.com/shorts/${v.id}` : `https://www.youtube.com/watch?v=${v.id}`,
    title: v.title, channel: v.channel, thumbnail_url: v.thumbnail_url, kind: v.kind, reason, source: "yt_search",
    duration: v.duration, views: v.views };
}
