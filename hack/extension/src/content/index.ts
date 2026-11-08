import { backendFetch, type Counters, type Verdict, type VideoMeta } from "../shared/api";
import { Overlay } from "../overlay/overlay";
import { pickAdapter, type Adapter } from "./adapters";
import { ReplacementCard, pageIsDark, TOMATO_ICON, type Replacement } from "./replacements";
import { ytSearch, toReplacement, feedQueries, interleave, type TopicSpec, type YtVideo } from "./ytPool";

const adapter: Adapter = pickAdapter(location.hostname);
const overlay = new Overlay();

interface State {
  profileId: string;
  enabled: boolean;
  autoThrow: boolean;
  counters: Counters;
}

let state: State = { profileId: "", enabled: true, autoThrow: true, counters: { auto: 0, manual: 0, undone: 0, replaced: 0 } };
const processed = new Set<string>();            // platform|id sent to /classify
const hidden = new Set<string>();               // platform|id hidden (persisted)
const cardById = new Map<string, Element>();
const elCurrentId = new WeakMap<Element, string>(); // freshness: id currently shown in this element
const visibleSet = new Set<Element>();
const pendingVisible = new Map<string, VideoMeta>();
const pendingBg = new Map<string, VideoMeta>();
const unsurePending: VideoMeta[] = [];
let flushTimer: number | undefined;
let refineTimer: number | undefined;
let classifyInFlight = 0;
const stats = { detected: 0, classified: 0, pending: 0, inflight: 0, queue: 0, lastLatency: 0 };
(window as any).__tomateStats = stats;

const VEIL_CSS = `:host{position:absolute;inset:0;pointer-events:none;z-index:3}
.v{position:absolute;inset:0;backdrop-filter:blur(9px) saturate(.4);background:oklch(0.25 0.03 60 / .38);border-radius:8px;display:flex;align-items:flex-end;padding:8px}
.l{font:600 12px "Nunito Sans",system-ui;color:oklch(0.96 0.01 80);background:oklch(0.3 0.02 60/.6);border-radius:999px;padding:3px 10px}`;

function veil(card: Element) {
  const el = card as HTMLElement;
  if (el.querySelector(":scope > .tomate-veil-host")) return;
  if (getComputedStyle(el).position === "static") el.style.position = "relative";
  const host = document.createElement("div");
  host.className = "tomate-veil-host";
  const sh = host.attachShadow({ mode: "open" });
  const st = document.createElement("style");
  st.textContent = VEIL_CSS;
  const v = document.createElement("div");
  v.className = "v";
  v.innerHTML = '<span class="l">Tomate en route…</span>';
  sh.append(st, v);
  el.appendChild(host);
}

function unveilsAll(card: Element) {
  card.querySelector(":scope > .tomate-veil-host")?.remove();
  card.querySelector(":scope > .tomate-qb-host")?.remove();
  card.querySelector(":scope > .tomate-strip-host")?.remove();
  card.querySelector(":scope > .tomate-replacement")?.remove();
  const el = card as HTMLElement;
  delete el.dataset.tomateHidden;
  delete el.dataset.tomateHiddenId;
  el.style.display = "";
}

function key(m: VideoMeta) { return `${m.platform}|${m.id}`; }

/** Panel stores `enabled` per platform ({youtube: true, ...}); older builds stored a boolean. */
function enabledFor(v: unknown): boolean {
  if (v && typeof v === "object") return (v as Record<string, boolean>)[adapter.platform] !== false;
  return v !== false;
}

async function loadState() {
  const s = (await chrome.storage.local.get(["profileId", "enabled", "autoThrow", "counters", "charPos", "hidden:" + adapter.platform])) as Record<string, any>;
  state.profileId = s.profileId ?? "";
  state.enabled = enabledFor(s.enabled);
  state.autoThrow = s.autoThrow !== false;
  state.counters = s.counters ?? state.counters;
  for (const k of (s["hidden:" + adapter.platform] ?? [])) hidden.add(k);
  overlay.setProfile(!!state.profileId && state.enabled);
  if (s.charPos) overlay.setPos(s.charPos);
  updateBadge();
}

async function persistHidden() {
  await chrome.storage.local.set({ ["hidden:" + adapter.platform]: [...hidden] });
}

async function bump(field: keyof Counters) {
  (state.counters[field] as number)++;
  await chrome.storage.local.set({ counters: state.counters });
  updateBadge();
}

function updateBadge() {
  const c = state.counters;
  void chrome.runtime.sendMessage({ kind: "badge", count: (c.auto || 0) + (c.manual || 0) - (c.undone || 0) }).catch(() => {});
}

function hideInstant(card: Element, id: string) {
  const el = card as HTMLElement;
  el.style.display = "none";
  el.dataset.tomateHiddenId = id;
  el.dataset.tomateHidden = "1";
}

/* ---------- scanning & freshness ---------- */
function scan() {
  if (!state.enabled) return;
  for (const card of adapter.findCards(document)) {
    const meta = adapter.extract(card);
    if (!meta) continue;
    const k = key(meta);
    const prev = elCurrentId.get(card);
    if (prev && prev !== meta.id) {
      // recycled element showing a new video — wipe our state on it
      unveilsAll(card);
      stats.detected++; // counts as a fresh tile
    }
    elCurrentId.set(card, meta.id);
    if (processed.has(k)) {
      // still hidden only if OUR marker matches current id
      if (hidden.has(k) && (card as HTMLElement).dataset.tomateHiddenId !== meta.id && !card.querySelector(".tomate-replacement")) {
        hideInstant(card, meta.id);
      }
      continue;
    }
    processed.add(k);
    cardById.set(k, card);
    stats.detected++;
    if (hidden.has(k)) { hideInstant(card, meta.id); continue; }
    if (!state.profileId) continue;
    (visibleSet.has(card) ? pendingVisible : pendingBg).set(k, meta);
    stats.pending++;
  }
  scheduleFlush();
}

/* ---------- visibility ---------- */
const io = new IntersectionObserver((entries) => {
  for (const e of entries) {
    const el = e.target as Element;
    if (e.isIntersecting) visibleSet.add(el); else visibleSet.delete(el);
  }
}, { rootMargin: "100% 0px" });

function observeCard(el: Element) { io.observe(el); }

/* ---------- classify ---------- */
function scheduleFlush() {
  if (flushTimer !== undefined) return;
  flushTimer = window.setTimeout(flush, 80);
}

async function flush() {
  flushTimer = undefined;
  if (classifyInFlight >= 3 || (!pendingVisible.size && !pendingBg.size) || !state.profileId) {
    if ((pendingVisible.size || pendingBg.size) && classifyInFlight < 3) return;
    if (classifyInFlight >= 3) { flushTimer = window.setTimeout(flush, 100); return; }
  }
  const src = pendingVisible.size ? pendingVisible : pendingBg;
  const batch = [...src.values()].slice(0, 8);
  for (const m of batch) src.delete(key(m));
  if (!batch.length) return;
  classifyInFlight++;
  stats.inflight = classifyInFlight;
  try {
    const t0 = performance.now();
    const resp = await backendFetch<{ verdicts: Verdict[]; timing_ms?: { total: number } }>("/classify", {
      method: "POST", body: { profile_id: state.profileId, videos: batch },
    });
    stats.lastLatency = Math.round(performance.now() - t0);
    const verdicts = Array.isArray(resp) ? resp as unknown as Verdict[] : resp.verdicts;
    for (const vd of verdicts) {
      stats.classified++;
      stats.pending--;
      const card = cardById.get(`${adapter.platform}|${vd.id}`) ?? cardById.get(`generic|${vd.id}`);
      if (!card) continue;
      if (vd.verdict === "off") {
        veil(card); // instant cover regardless of animation timing
        if (state.autoThrow && !(card as HTMLElement).dataset.tomateHidden) {
          hidden.add(`${adapter.platform}|${vd.id}`);
          void persistHidden();
          void backendFetch("/feedback", { method: "POST", body: { profile_id: state.profileId, video: findMeta(vd.id), action: "auto_tomato" } }).catch(() => {});
          void bump("auto");
          overlay.enqueue({ card, reason: vd.reason || "Hors sujet", videoId: vd.id });
          scheduleReplacement(card, vd.reason);
        }
      } else if (vd.verdict === "unsure") {
        if (vd.confidence < 0.6) {
          const m = findMeta(vd.id);
          if (m) { unsurePending.push(m); scheduleRefine(); }
        } else {
          overlay.markUnsure(card, vd.reason, unsureHooks());
        }
      }
      if (overlay.queue.length === 0 && classifyInFlight === 0 && !overlay.throwing) maybeCelebrate();
    }
  } catch {
    for (const m of batch) { (visibleSet.has(cardById.get(key(m))!) ? pendingVisible : pendingBg).set(key(m), m); processed.delete(key(m)); }
  } finally {
    classifyInFlight--;
    stats.inflight = classifyInFlight;
    overlay.pendingClassify = classifyInFlight;
    scheduleFlush();
    scheduleRefine();
  }
}

function scheduleRefine() {
  if (refineTimer !== undefined || !unsurePending.length) return;
  refineTimer = window.setTimeout(async () => {
    refineTimer = undefined;
    const batch = unsurePending.splice(0, 8);
    try {
      const resp = await backendFetch<{ verdicts: Verdict[] }>("/classify/refine", {
        method: "POST", body: { profile_id: state.profileId, videos: batch },
      });
      for (const vd of resp.verdicts ?? []) {
        const card = cardById.get(`${adapter.platform}|${vd.id}`) ?? cardById.get(`generic|${vd.id}`);
        if (!card) continue;
        if (vd.verdict === "off") {
          veil(card);
          if (state.autoThrow && !(card as HTMLElement).dataset.tomateHidden) {
            hidden.add(`${adapter.platform}|${vd.id}`);
            void persistHidden();
            void bump("auto");
            overlay.enqueue({ card, reason: vd.reason || "Hors sujet", videoId: vd.id });
            scheduleReplacement(card, vd.reason);
          }
        } else {
          overlay.markUnsure(card, vd.reason, unsureHooks());
        }
      }
    } catch { /* keep unsure state */ }
    scheduleRefine();
  }, 600);
}

function unsureHooks() {
  return {
    onKeep: (c: Element) => { const m = adapter.extract(c); if (m && state.profileId) void backendFetch("/feedback", { method: "POST", body: { profile_id: state.profileId, video: m, action: "undo" } }).catch(() => {}); },
    onTomato: (c: Element) => { void manualThrow(c); },
  };
}

function findMeta(id: string): VideoMeta | undefined {
  for (const [k, card] of cardById) {
    if (k.endsWith("|" + id)) return adapter.extract(card) ?? undefined;
  }
  return undefined;
}

function maybeCelebrate() {
  overlay.celebrate();
}

/* ---------- YouTube search pool (shared by tile replacements + home feed shelf) ---------- */
const onYouTube = location.hostname.includes("youtube.com");
let profileInclude: TopicSpec[] = [];

async function loadProfileInclude() {
  const { profile } = (await chrome.storage.local.get("profile")) as Record<string, any>;
  profileInclude = profile?.include ?? [];
}

function onPageIds(): string[] { return [...processed].map((k) => k.split("|")[1]); }

/** One round of profile-derived YouTube searches, round-robin mixed, deduped, gated by /classify (on, conf >= .7). */
async function ytPool(round: number, exclude: Set<string>, kinds: "video" | "any" = "any"): Promise<Replacement[]> {
  const qs = feedQueries(profileInclude, round);
  if (!qs.length || !state.profileId) return [];
  const lists = await Promise.all(qs.map((q) => ytSearch(q).catch(() => [] as YtVideo[])));
  const seen = new Set<string>();
  const cands = interleave(lists).filter((v) => v.id && v.title && (kinds === "any" || v.kind === kinds)
    && !seen.has(v.id) && !exclude.has(v.id) && !hidden.has(`youtube|${v.id}`) && !!seen.add(v.id)).slice(0, 40);
  if (!cands.length) return [];
  const resp = await backendFetch<{ verdicts: Verdict[] }>("/classify", {
    method: "POST", body: { profile_id: state.profileId,
      videos: cands.map((v) => ({ platform: "youtube", id: v.id, url: toReplacement(v, "").url,
        title: v.title, channel: v.channel, description: "", hashtags: [] })) },
  });
  const ok = new Map((resp.verdicts ?? []).filter((v) => v.verdict === "on" && v.confidence >= 0.7).map((v) => [v.id, v]));
  return cands.filter((v) => ok.has(v.id)).map((v) => toReplacement(v, ok.get(v.id)!.reason || "dans le sujet"));
}

/* ---------- replacements ---------- */
const buffer: Replacement[] = [];
let bufferLoading = false;
let bufferRound = 1; // odd rounds; the home shelf uses even ones so both get different queries

async function refillBuffer(force = false) {
  if (!state.profileId || bufferLoading || (buffer.length >= 10 && !force)) return;
  bufferLoading = true;
  try {
    if (onYouTube && profileInclude.length) {
      const exclude = new Set([...buffer.map((b) => b.id), ...feedIds, ...onPageIds()]);
      const items = await ytPool(bufferRound, exclude);
      bufferRound += 2;
      buffer.push(...items);
      if (items.length) return;
    }
    const items = await backendFetch<Replacement[]>("/replacements", {
      method: "POST",
      body: { profile_id: state.profileId,
              platform: adapter.platform === "generic" ? "youtube" : adapter.platform,
              exclude_ids: [...hidden].map((k) => k.split("|")[1]), count: 10 },
    });
    buffer.push(...items);
  } catch { /* keep slim strip */ } finally {
    bufferLoading = false;
  }
}

/** Prefer a replacement of the same shape (Short for a Short tile) that isn't already in the home shelf. */
function takeReplacement(card: Element): Replacement | undefined {
  const url = adapter.extract(card)?.url ?? "";
  const wantShort = /\/shorts\//.test(url);
  let i = buffer.findIndex((r) => !feedIds.has(r.id) && (adapter.platform !== "youtube" || (r.kind === "short") === wantShort));
  if (i < 0) i = buffer.findIndex((r) => !feedIds.has(r.id));
  return i < 0 ? undefined : buffer.splice(i, 1)[0];
}

function scheduleReplacement(card: Element, reason: string) {
  const rect = card.getBoundingClientRect();
  setTimeout(() => {
    const rep = takeReplacement(card);
    if (!rep) { void refillBuffer(); return; }
    const rc = new ReplacementCard(rep, rect, pageIsDark());
    rc.mountAfter(card);
    state.counters.replaced = (state.counters.replaced ?? 0) + 1;
    void chrome.storage.local.set({ counters: state.counters });
    updateBadge();
    void refillBuffer();
    rc.onUndo = () => {
      buffer.unshift(rep);
      rc.remove();
      overlay.restore(card);
      const meta = adapter.extract(card);
      if (meta) {
        hidden.delete(key(meta));
        void persistHidden();
        void bump("undone");
        if (state.profileId) void backendFetch("/feedback", { method: "POST", body: { profile_id: state.profileId, video: meta, action: "undo" } }).catch(() => {});
      }
    };
  }, 400);
}

/* ---------- manual throw ---------- */
async function manualThrow(card: Element) {
  const meta = adapter.extract(card);
  if (!meta) return;
  hidden.add(key(meta));
  void persistHidden();
  void bump("manual");
  if (state.profileId) {
    void backendFetch("/feedback", { method: "POST", body: { profile_id: state.profileId, video: meta, action: "tomato" } }).catch(() => {});
  }
  veil(card);
  await overlay.throwAt(card, "Lancée à la main", meta.id);
  scheduleReplacement(card, "lancée à la main");
}

/* ---------- HUD ---------- */
let hud: HTMLElement | null = null;
function toggleHud() {
  if (hud) { hud.remove(); hud = null; return; }
  const host = document.createElement("div");
  host.style.cssText = "position:fixed;left:8px;bottom:8px;z-index:2147483647";
  hud = host.attachShadow({ mode: "open" }) as unknown as HTMLElement;
  const d = document.createElement("pre");
  (hud as unknown as ShadowRoot).appendChild(d);
  d.style.cssText = "font:11px/1.5 ui-monospace,monospace;background:oklch(0.22 0.02 60 / .92);color:oklch(0.8 0.12 145);padding:8px 10px;border-radius:8px;margin:0";
  document.documentElement.appendChild(host);
  const upd = () => {
    if (!hud) return;
    stats.queue = overlay.queue.length;
    d.textContent = `detected ${stats.detected} | classified ${stats.classified} | pending ${stats.pending}\ninflight ${stats.inflight} | throwQ ${stats.queue} | last ${stats.lastLatency}ms`;
    setTimeout(upd, 500);
  };
  upd();
}

/* ---------- triggers ---------- */
let moTimer: number | undefined;
const mo = new MutationObserver((muts) => {
  if (moTimer !== undefined) return;
  moTimer = window.setTimeout(() => {
    moTimer = undefined;
    // also observe new cards for visibility
    for (const c of adapter.findCards(document)) observeCard(c);
    scan();
  }, 150);
});
mo.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["href"] });

let scrollTimer: number | undefined;
window.addEventListener("scroll", () => {
  if (scrollTimer !== undefined) return;
  scrollTimer = window.setTimeout(() => { scrollTimer = undefined; scan(); scheduleFlush(); }, 200);
}, { passive: true });

for (const ev of ["yt-navigate-finish", "yt-page-data-updated", "popstate", "visibilitychange"]) {
  document.addEventListener(ev, () => { scan(); tickShelf(); }, true);
}
setInterval(() => { if (!document.hidden) scan(); }, 1500);

chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.kind === "userThrow") overlay.toggleThrowMode();
});

chrome.storage.onChanged.addListener((changes) => {
  if (changes.profileId) { state.profileId = changes.profileId.newValue as string ?? ""; overlay.setProfile(!!state.profileId && state.enabled); processed.clear(); scan(); void refillBuffer(); }
  if (changes.enabled) { state.enabled = enabledFor(changes.enabled.newValue); overlay.setProfile(!!state.profileId && state.enabled); tickShelf(); }
  if (changes.profile || changes.profileId) {
    void loadProfileInclude().then(() => { buffer.length = 0; resetFeed(); tickShelf(); void refillBuffer(); });
  }
  if (changes.replaceHome) { replaceHome = !!changes.replaceHome.newValue; tickShelf(); }
  if (changes.autoThrow) state.autoThrow = changes.autoThrow.newValue !== false;
});

overlay.bindThrowMode((el) => {
  const card = el.closest?.("ytd-rich-item-renderer, ytd-video-renderer, ytd-compact-video-renderer, ytd-reel-item-renderer, ytm-shorts-lockup-view-model, yt-lockup-view-model, article, [data-e2e='recommend-list-item-container'], [data-e2e='explore-item'], .fx-card");
  return card ?? null;
});
overlay.onManualThrow = (card) => { void manualThrow(card); };
overlay.onUndo = (card) => {
  const meta = adapter.extract(card);
  if (meta) {
    hidden.delete(key(meta));
    void persistHidden();
    void bump("undone");
    if (state.profileId) {
      void backendFetch("/feedback", { method: "POST", body: { profile_id: state.profileId, video: meta, action: "undo" } }).catch(() => {});
    }
  }
  unveilsAll(card);
};
overlay.onSleepClick = () => { void chrome.runtime.sendMessage({ kind: "openPanel" }).catch(() => {}); };
overlay.onMoved = (pos) => { void chrome.storage.local.set({ charPos: pos }); };

// dev harness bridge — page dispatches CustomEvent('tomate:debug', {detail:{cmd,arg}})
document.addEventListener("tomate:debug", ((e: CustomEvent) => {
  const { cmd, arg } = e.detail ?? {};
  const card = arg ? document.querySelector(arg) : null;
  if (cmd === "state") overlay.setProfile(arg !== "sleep");
  if (cmd === "sleep") { overlay.setProfile(false); }
  if (cmd === "celebrate") overlay.celebrate();
  if (cmd === "aim" && card) (overlay as any).spot(card);
  if (cmd === "throw" && card) void overlay.throwAt(card, "démo", "debug");
}) as EventListener);

document.addEventListener("keydown", (e) => {
  if (e.shiftKey && (e.key === "T" || e.key === "t")) { e.preventDefault(); toggleHud(); }
});

/* ---------- "Ton feed Tomate": home shelf (and optional full home replacement) ---------- */
const FEED_MIN = 8;
let feed: Replacement[] = [];
const feedIds = new Set<string>(); // everything shown in the shelf this session (never re-served)
let feedRound = 0;
let feedLoading = false;
let feedMsg = "";
let feedVersion = 0;
let shelfVersion = -1;
let shelf: HTMLElement | null = null;
let replaceHome = false;
let hiddenGrid: HTMLElement | null = null;

const isHome = () => onYouTube && location.pathname === "/";

function resetFeed() {
  feed = []; feedIds.clear(); feedRound = 0; feedMsg = ""; feedVersion++;
}

async function loadFeed(mode: "fill" | "refresh" | "more") {
  if (feedLoading || !state.profileId) return;
  if (!profileInclude.length) { feedMsg = "Crée ton profil dans le panneau Tomate pour remplir ce feed."; feedVersion++; tickShelf(); return; }
  feedLoading = true; feedMsg = ""; feedVersion++; tickShelf();
  try {
    const exclude = new Set([...feedIds, ...buffer.map((b) => b.id), ...onPageIds()]);
    const got: Replacement[] = [];
    for (let tries = 0; tries < 3 && got.length < FEED_MIN; tries++) {
      const r = await ytPool(feedRound, exclude, "video");
      feedRound += 2;
      for (const x of r) { exclude.add(x.id); got.push(x); }
    }
    for (const x of got) feedIds.add(x.id);
    if (mode === "refresh" && got.length) feed = got; else feed.push(...got);
    if (!got.length) feedMsg = feed.length ? "Rien de neuf pour l'instant." : "Aucune vidéo trouvée — réessaie « Actualiser ».";
  } catch {
    feedMsg = "Backend Tomate injoignable.";
  } finally {
    feedLoading = false; feedVersion++; tickShelf();
  }
}

const SHELF_CSS = `:host{display:block;margin:16px 24px 8px;font-family:"Roboto","Arial",sans-serif;color:var(--yt-spec-text-primary,#0f0f0f)}
.bar{display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap}
.t{font:700 20px/1.2 "Roboto","Arial",sans-serif;display:flex;align-items:center;gap:8px}
.st{font-size:13px;color:var(--yt-spec-text-secondary,#606060)}
button{font:500 14px "Roboto","Arial",sans-serif;border:0;background:var(--yt-spec-badge-chip-background,rgba(0,0,0,.05));color:inherit;border-radius:18px;padding:8px 16px;cursor:pointer}
button:hover{background:var(--yt-spec-button-chip-background-hover,rgba(0,0,0,.1))}
button:disabled{opacity:.5;cursor:default}
.bar button{margin-left:auto}
.row{display:grid;grid-auto-flow:column;grid-auto-columns:300px;gap:16px;overflow-x:auto;scroll-snap-type:x proximity;padding-bottom:8px}
.full .row{grid-auto-flow:row;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));grid-auto-columns:auto;overflow:visible;row-gap:28px}
.row>*{scroll-snap-align:start;min-width:0}
.skel{aspect-ratio:16/9;border-radius:12px;background:var(--yt-spec-10-percent-layer,rgba(0,0,0,.08));animation:p 1s ease-in-out infinite alternate}
@keyframes p{to{opacity:.45}}
.more{display:none;margin:24px auto}
.full .more{display:block}`;

function buildShelf(): HTMLElement {
  const host = document.createElement("div");
  host.className = "tomate-shelf";
  const sh = host.attachShadow({ mode: "open" });
  sh.innerHTML = `<style>${SHELF_CSS}</style><div class="wrap">
    <div class="bar"><span class="t">${TOMATO_ICON(22)}Ton feed Tomate</span><span class="st"></span><button class="refresh">Actualiser</button></div>
    <div class="row"></div>
    <button class="more">Plus de vidéos</button></div>`;
  sh.querySelector<HTMLButtonElement>(".refresh")!.onclick = () => { void loadFeed("refresh"); };
  sh.querySelector<HTMLButtonElement>(".more")!.onclick = () => { void loadFeed("more"); };
  return host;
}

function restoreGrid() {
  if (hiddenGrid) { hiddenGrid.style.display = ""; hiddenGrid = null; }
}

/** Idempotent: called on SPA navigation, storage changes and a 1s tick. Only rebuilds cards when the feed changed. */
function tickShelf() {
  if (!isHome() || !state.enabled || !state.profileId) { shelf?.remove(); restoreGrid(); return; }
  const anchor = document.querySelector<HTMLElement>('ytd-browse[page-subtype="home"] > ytd-two-column-browse-results-renderer');
  if (!anchor?.parentElement) return;
  shelf ??= buildShelf();
  if (shelf.nextElementSibling !== anchor) anchor.parentElement.insertBefore(shelf, anchor);
  if (replaceHome) { anchor.style.display = "none"; hiddenGrid = anchor; } else restoreGrid();
  if (!feed.length && !feedLoading && !feedMsg) void loadFeed("fill");

  const sh = shelf.shadowRoot!;
  sh.querySelector(".wrap")!.classList.toggle("full", replaceHome);
  sh.querySelectorAll<HTMLButtonElement>("button").forEach((b) => { b.disabled = feedLoading; });
  sh.querySelector(".st")!.textContent = feedLoading ? "Tomate cherche dans tes sujets…" : feedMsg || `${feed.length} vidéos dans ton sujet`;
  if (shelfVersion === feedVersion) return;
  shelfVersion = feedVersion;
  const row = sh.querySelector(".row")!;
  row.replaceChildren();
  if (!feed.length && feedLoading) {
    for (let i = 0; i < 6; i++) { const d = document.createElement("div"); d.className = "skel"; row.appendChild(d); }
    return;
  }
  const dark = pageIsDark();
  for (const rep of feed) row.appendChild(new ReplacementCard(rep, null, dark, "shelf").host);
}

void chrome.storage.local.get("replaceHome").then((x) => { replaceHome = !!x.replaceHome; tickShelf(); });

void loadState().then(async () => {
  await loadProfileInclude();
  for (const c of adapter.findCards(document)) observeCard(c);
  scan();
  if (onYouTube) {
    tickShelf();
    setInterval(() => { if (!document.hidden) tickShelf(); }, 1000);
  }
  void refillBuffer();
});
