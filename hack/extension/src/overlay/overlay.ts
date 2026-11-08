// Overlay: Shadow-DOM root + tomato-farmer character + throw queue + throw mode.
import { CHAR_SVG, TOMATO_SVG, splatSvg } from "./character";

const FONTS = (base: string) => `
@font-face{font-family:"Fredoka";src:url("${base}fonts/fredoka-latin-600-normal.woff2") format("woff2");font-weight:600;font-display:swap}
@font-face{font-family:"Nunito Sans";src:url("${base}fonts/nunito-sans-latin-800-normal.woff2") format("woff2");font-weight:800;font-display:swap}
`;

const CSS = `
:host { all: initial; --t-red: oklch(0.62 0.19 38); --t-red-deep: oklch(0.50 0.16 38); --t-green: oklch(0.55 0.13 145); --t-surface: oklch(0.97 0.02 90); --t-ink: oklch(0.32 0.03 60); --t-ink-mut: oklch(0.55 0.03 60); --t-r-md: 10px; --t-r-pill: 999px; --t-sh-2: 0 4px 14px oklch(0.3 0.02 60 / .16); --t-sh-3: 0 10px 30px oklch(0.3 0.02 60 / .2); --t-font-display: "Fredoka", system-ui, sans-serif; --t-font-ui: "Nunito Sans", system-ui, sans-serif; }
.wrap { position: fixed; inset: 0; pointer-events: none; z-index: 2147483646; font-family: var(--t-font-ui); }
.char { position: fixed; width: 120px; pointer-events: auto; cursor: grab; touch-action: none; }
.char.dragging { cursor: grabbing; }
.char svg { display: block; width: 100%; height: auto; }
.char.left svg { transform: scaleX(-1); }
.char.sleeping { opacity: .6; filter: saturate(.4); }
.char.sleeping .c-eyes-open { display:none; }
.char .c-zzz { display: none; }
.char.sleeping .c-zzz { display: block; }
.bubble {
  position: fixed; background: var(--t-surface); border: 1.5px solid oklch(0.72 0.03 70); border-radius: var(--t-r-pill) var(--t-r-pill) var(--t-r-pill) var(--t-r-md);
  padding: 8px 14px; font: 600 15px var(--t-font-ui); color: var(--t-ink); max-width: 230px;
  pointer-events: auto; box-shadow: var(--t-sh-2), inset 0 1px 0 rgba(255,255,255,.5); z-index: 2147483647;
  transform-origin: bottom left; animation: tpop .22s cubic-bezier(.2,.9,.3,1.2);
}
@keyframes tpop { from { transform: scale(.4); opacity: 0 } to { transform: scale(1); opacity: 1 } }
.bubble::after { content:""; position: absolute; bottom: -11px; left: 16px; width: 14px; height: 12px; background: var(--t-surface); clip-path: polygon(0 0, 100% 0, 20% 100%); border-left: 1.5px solid oklch(0.72 0.03 70); }
.tomato { position: fixed; width: 28px; height: 28px; pointer-events: none; z-index: 2147483647; }
.tshadow { position: fixed; width: 20px; height: 6px; border-radius: 50%; background: rgba(0,0,0,.18); pointer-events: none; z-index: 2147483646; }
.splat { position: fixed; pointer-events: auto; cursor: pointer; transform: translate(-50%,-50%); z-index: 2147483646; }
.splat svg { display:block; }
.splat .reason {
  position: absolute; top: 100%; left: 50%; transform: translateX(-50%); margin-top: 6px;
  background: oklch(0.28 0.03 60 / .95); color: oklch(0.96 0.01 80); border-radius: 999px;
  padding: 5px 12px; font: 600 13px var(--t-font-ui); white-space: nowrap;
  max-width: 320px; overflow: hidden; text-overflow: ellipsis; box-shadow: var(--t-sh-2);
}
.splat .undo { color: #ffd27d; font-weight: 700; }
.qbadge {
  position: absolute; top: 6px; right: 6px; z-index: 5;
  width: 24px; height: 24px; border-radius: 50%; background: oklch(0.82 0.14 90); color: oklch(0.3 0.03 60);
  font: 700 15px/24px var(--t-font-ui); text-align: center; cursor: pointer; pointer-events: auto;
  box-shadow: var(--t-sh-2); border: 2px solid oklch(0.96 0.02 90);
}
.qmenu {
  position: fixed; background: var(--t-surface); border: 1.5px solid oklch(0.72 0.03 70); border-radius: 12px;
  padding: 4px; display: flex; flex-direction: column; min-width: 120px; z-index: 2147483647;
  pointer-events: auto; box-shadow: var(--t-sh-3);
}
.qmenu button { font: 700 14px var(--t-font-ui); background: none; border: 0; padding: 7px 12px; text-align: left; cursor: pointer; border-radius: 8px; color: var(--t-ink); }
.qmenu button:hover { background: oklch(0.9 0.05 90); }
.qmenu .reason { font: 400 12px var(--t-font-ui); color: var(--t-ink-mut); padding: 4px 12px; max-width: 220px; }
.fx-highlight { outline: 3px dashed #e74c3c !important; outline-offset: -3px; }
.reticle { position: absolute; inset: 0; pointer-events: none; z-index: 4; }
.reticle::before, .reticle::after, .reticle i, .reticle b { content:""; position: absolute; width: 22px; height: 22px; border: 3px solid #e74c3c; }
.reticle::before { top:6px; left:6px; border-right:0; border-bottom:0; }
.reticle::after { top:6px; right:6px; border-left:0; border-bottom:0; }
.reticle i { bottom:6px; left:6px; border-right:0; border-top:0; }
.reticle b { bottom:6px; right:6px; border-left:0; border-top:0; }
.particle { position: fixed; width: 7px; height: 7px; border-radius: 50%; background: #d63031; pointer-events: none; z-index: 2147483647; }
.leaf { position: fixed; width: 12px; height: 12px; pointer-events: none; z-index: 2147483646; }
.cursor-tomato { position: fixed; width: 30px; height: 30px; pointer-events: none; z-index: 2147483647; }
:host .strip { display:flex; align-items:center; gap:8px; height:28px; padding:0 12px; margin:0;
  background:oklch(0.95 0.03 40); border:1px dashed var(--t-red); border-radius:999px; font:600 13px var(--t-font-ui); color:var(--t-red-deep);
  cursor:pointer; overflow:hidden; }
:host .strip svg { flex:none; }
:host .strip .undo { margin-left:auto; color:var(--t-red); font-weight:800; }
`;

const BUBBLES = {
  throw: ["Hors sujet !", "Pas pour toi, ça.", "Splash.", "Encore un, allez.", "Prends ça."],
  drama: ["Encore un drama…", "Du drama ? Tomate.", "Les célébrités ailleurs, merci."],
  celebrate: ["Tout est bon !", "Que du bon, là.", "Fil propre. Beau travail."],
  aim: ["Tss…", "Celui-là non.", "Hmm, non."],
  undo: ["OK, pardon.", "Bien vu, je retire."],
  sleep: ["Zzz… crée un profil pour me réveiller."],
  keep: ["D'accord, on garde."],
};

const pick = (arr: string[]) => arr[Math.floor(Math.random() * arr.length)];
const SPRING = "cubic-bezier(.34,1.45,.5,1)";

type Mouth = "smile" | "o" | "grin" | "smirk" | "sleep";

export interface ThrowRequest { card: Element; reason: string; videoId: string; retries?: number }
export interface BadgeHooks { onKeep?: (card: Element) => void; onTomato?: (card: Element) => void }

export class Overlay {
  root: ShadowRoot;
  char: HTMLElement;
  queue: ThrowRequest[] = [];
  throwing = false;
  throwMode = false;
  hasProfile = false;
  pendingClassify = 0;
  onManualThrow: (card: Element) => void = () => {};
  onUndo: (card: Element, videoId: string) => void = () => {};
  onSleepClick: () => void = () => {};
  onMoved: (pos: { right: number; bottom: number; left: boolean }) => void = () => {};
  reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  private blinkTimer: number | undefined;
  private lookTimer: number | undefined;
  private part = (sel: string) => this.char.querySelector(sel) as SVGGElement | null;
  private _pos = { right: 24, bottom: 24, left: false };

  constructor() {
    const host = document.createElement("div");
    host.id = "tomate-overlay-host";
    document.documentElement.appendChild(host);
    this.root = host.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = FONTS(chrome.runtime.getURL("")) + CSS;
    const wrap = document.createElement("div");
    wrap.className = "wrap";
    this.root.append(style, wrap);
    this.char = document.createElement("div");
    this.char.className = "char sleeping";
    this.char.innerHTML = CHAR_SVG;
    this.char.title = "Tomate";
    wrap.appendChild(this.char);
    this.applyPos();
    this.char.addEventListener("click", () => {
      if (this.hasProfile) this.toggleThrowMode();
      else this.onSleepClick();
    });
    this.initDrag();
    this.initIdle();
  }

  /* ---------------- position & drag ---------------- */
  applyPos() {
    const p = this._pos;
    this.char.style.right = `${p.right}px`;
    this.char.style.bottom = `${p.bottom}px`;
    this.char.classList.toggle("left", p.left);
  }
  setPos(p: { right: number; bottom: number; left: boolean }) { this._pos = p; this.applyPos(); }

  private initDrag() {
    let startX = 0, startY = 0, moved = false, baseR = 0, baseB = 0;
    this.char.addEventListener("pointerdown", (e) => {
      moved = false; startX = e.clientX; startY = e.clientY;
      baseR = this._pos.right; baseB = this._pos.bottom;
      this.char.classList.add("dragging");
      this.char.setPointerCapture(e.pointerId);
    });
    this.char.addEventListener("pointermove", (e) => {
      if (!this.char.classList.contains("dragging")) return;
      const dx = e.clientX - startX, dy = e.clientY - startY;
      if (Math.abs(dx) + Math.abs(dy) > 6) moved = true;
      if (moved) {
        this._pos = { right: Math.max(0, baseR - dx), bottom: Math.max(0, baseB - dy), left: baseR - dx > innerWidth / 2 };
        this.applyPos();
      }
    });
    this.char.addEventListener("pointerup", () => {
      this.char.classList.remove("dragging");
      if (moved) this.onMoved(this._pos);
    });
    this.char.addEventListener("click", (e) => { if (moved) e.stopImmediatePropagation(); }, true);
  }

  /* ---------------- idle life ---------------- */
  private initIdle() {
    const loop = () => {
      if (this.reduced || !this.hasProfile) return;
      // breathing + weight shift
      this.part(".c-body-all")?.animate(
        [{ transform: "scaleY(1) rotate(0deg)" }, { transform: "scaleY(1.028) rotate(.6deg)" }, { transform: "scaleY(1) rotate(0deg)" }],
        { duration: 2600, easing: "ease-in-out", iterations: 1 });
      this.part(".c-basket")?.animate(
        [{ transform: "rotate(0)" }, { transform: "rotate(2.5deg)" }, { transform: "rotate(0)" }],
        { duration: 2600, easing: "ease-in-out", delay: 120 });
      // blink via eyelids
      for (const lid of [".c-lid-l", ".c-lid-r"]) {
        (this.char.querySelector(lid) as SVGElement | null)
          ?.animate([{ opacity: 0 }, { opacity: 1, offset: .45 }, { opacity: 0 }], { duration: 150 });
      }
      // occasional micro-action
      const r = Math.random();
      if (r < 0.12) {
        this.part(".c-hat")?.animate([{ transform: "rotate(0)" }, { transform: "rotate(-7deg) translateY(-2px)" }, { transform: "rotate(0)" }], { duration: 700, easing: SPRING });
        this.part(".c-arm-l")?.animate([{ transform: "rotate(0)" }, { transform: "rotate(-30deg)" }, { transform: "rotate(0)" }], { duration: 600 });
      } else if (r < 0.22) {
        this.part(".c-head")?.animate([{ transform: "rotate(0)" }, { transform: "rotate(9deg) translateX(-3px)" }, { transform: "rotate(0)" }], { duration: 800, easing: "ease-in-out" });
      } else if (r < 0.3) {
        this.part(".c-legs")?.animate([{ transform: "translateY(0)" }, { transform: "translateY(-2px)" }, { transform: "translateY(0)" }], { duration: 160, iterations: 3 });
      }
      this.blinkTimer = window.setTimeout(loop, 2000 + Math.random() * 3000);
    };
    const look = () => {
      if (this.reduced || !this.hasProfile) return;
      const dx = (Math.random() - .5) * 6;
      for (const eye of [".c-eye-l", ".c-eye-r"]) {
        this.part(eye)?.animate([{ transform: `translateX(${dx}px)` }, { transform: "translateX(0)" }], { duration: 900, easing: "ease-in-out" });
      }
      this.lookTimer = window.setTimeout(look, 5000 + Math.random() * 5000);
    };
    this._startIdle = loop; this._startLook = look;
  }
  private _startIdle: () => void = () => {};
  private _startLook: () => void = () => {};

  setProfile(active: boolean) {
    this.hasProfile = active;
    this.char.classList.toggle("sleeping", !active);
    this.setMouth(active ? "smile" : "sleep");
    for (const lid of [".c-lid-l", ".c-lid-r"]) {
      (this.char.querySelector(lid) as SVGElement | null)?.animate([{ opacity: active ? 0 : 1 }], { duration: 200, fill: "forwards" });
    }
    if (active && !this.reduced) { this._startIdle(); this._startLook(); }
    if (!active) { clearTimeout(this.blinkTimer); clearTimeout(this.lookTimer); }
  }

  setMouth(m: Mouth, dur = 180) {
    for (const el of this.char.querySelectorAll(".c-mouth")) {
      const on = el.classList.contains(`c-m-${m}`);
      (el as SVGElement).animate([{ opacity: on ? 1 : 0 }], { duration: dur, fill: "forwards" });
    }
  }

  /* ---------------- speech ---------------- */
  bubble(text: string, ms = 3000) {
    if (!text) return;
    const b = document.createElement("div");
    b.className = "bubble";
    b.textContent = text;
    this.root.querySelector(".wrap")!.appendChild(b);
    const cr = this.char.getBoundingClientRect();
    b.style.left = `${Math.max(10, cr.left - b.offsetWidth - 14)}px`;
    b.style.top = `${Math.max(10, cr.top - b.offsetHeight - 10)}px`;
    setTimeout(() => b.remove(), ms);
  }

  /* ---------------- celebrating ---------------- */
  celebrate() {
    if (this.char.dataset.celebrating) return;
    this.char.dataset.celebrating = "1";
    this.bubble(pick(BUBBLES.celebrate), 2600);
    const body = this.part(".c-body-all");
    const hat = this.part(".c-hat");
    if (!this.reduced) {
      this.setMouth("grin");
      body?.animate([
        { transform: "translateY(0) scaleY(1) scaleX(1)" },
        { transform: "translateY(-18px) scaleY(1.06) scaleX(.96)", offset: .35 },
        { transform: "translateY(0) scaleY(.9) scaleX(1.08)", offset: .7 },
        { transform: "translateY(0) scaleY(1) scaleX(1)" },
      ], { duration: 600, easing: "ease-out", iterations: 2 });
      hat?.animate([{ transform: "translateY(0) rotate(0)" }, { transform: "translateY(-16px) rotate(-16deg)" }, { transform: "translateY(0) rotate(0)" }],
        { duration: 620, easing: SPRING, iterations: 2, delay: 90 });
      this.part(".c-basket")?.animate([{ transform: "rotate(0)" }, { transform: "rotate(6deg)" }, { transform: "rotate(0)" }], { duration: 650, easing: SPRING, delay: 140 });
      // tomato-leaf sparkles only (no confetti)
      for (let i = 0; i < 5; i++) {
        const l = document.createElement("div");
        l.className = "leaf";
        l.innerHTML = `<svg viewBox="0 0 12 12"><path d="M6 1 q5 2 4 7 q-5 -1 -4 -7z" fill="#27ae60"/></svg>`;
        const r = this.char.getBoundingClientRect();
        l.style.left = `${r.left + r.width / 2}px`;
        l.style.top = `${r.top}px`;
        this.root.querySelector(".wrap")!.appendChild(l);
        const dx = (i - 2) * 26;
        l.animate([
          { transform: "translate(0,0) rotate(0)", opacity: 1 },
          { transform: `translate(${dx}px, -50px) rotate(${dx * 4}deg)`, opacity: 0 },
        ], { duration: 800, easing: "ease-out" }).finished.then(() => l.remove());
      }
    }
    setTimeout(() => delete this.char.dataset.celebrating, 1400);
  }

  /* ---------------- spotting ---------------- */
  private spot(card: Element) {
    const cr = card.getBoundingClientRect();
    const r = this.char.getBoundingClientRect();
    const cx = cr.left + cr.width / 2 - (r.left + r.width / 2);
    const cy = cr.top + cr.height / 2 - (r.top + r.height / 2);
    const ang = Math.atan2(cy, cx);
    const head = this.part(".c-head");
    head?.animate([{ transform: `rotate(${Math.max(-0.35, Math.min(0.35, ang * .3))}rad)` }], { duration: 300, fill: "forwards" });
    for (const eye of [".c-eye-l", ".c-eye-r"]) {
      this.part(eye)?.animate([{ transform: `translate(${Math.cos(ang) * 2.4}px, ${Math.sin(ang) * 2}px)` }],
        { duration: 250, fill: "forwards" });
    }
    this.setMouth("o", 120);
    const browL = this.part(".c-brow-l"), browR = this.part(".c-brow-r");
    browL?.animate([{ transform: "rotate(14deg) translateY(1px)" }], { duration: 200, fill: "forwards" });
    browR?.animate([{ transform: "rotate(-14deg) translateY(1px)" }], { duration: 200, fill: "forwards" });
    const bang = this.char.querySelector(".c-bang") as SVGTextElement;
    bang?.animate([{ opacity: 0, transform: "translateY(6px) scale(.4)" }, { opacity: 1, transform: "translateY(0) scale(1.15)" }, { opacity: 0, transform: "translateY(-4px) scale(1)" }],
      { duration: 900, easing: "ease-out" });
    if (Math.random() < 0.5) this.bubble(/drama|célébrité|people/i.test("") ? pick(BUBBLES.drama) : pick(BUBBLES.aim), 1600);
  }

  /* ---------------- unsure badge ---------------- */
  markUnsure(card: Element, reason: string, hooks: BadgeHooks = {}) {
    const el = card as HTMLElement;
    if (el.querySelector(":scope > .tomate-qb-host")) return;
    if (getComputedStyle(el).position === "static") el.style.position = "relative";
    const host = document.createElement("div");
    host.className = "tomate-qb-host";
    const sh = host.attachShadow({ mode: "open" });
    const st = document.createElement("style");
    st.textContent = CSS;
    sh.appendChild(st);
    const badge = document.createElement("div");
    badge.className = "qbadge";
    badge.textContent = "?";
    badge.title = `Incertain : ${reason || "pas assez d'indices"}`;
    sh.appendChild(badge);
    el.appendChild(host);
    badge.addEventListener("click", (e) => {
      e.stopPropagation();
      sh.querySelectorAll(".qmenu").forEach((m) => m.remove());
      const menu = document.createElement("div");
      menu.className = "qmenu";
      const r = badge.getBoundingClientRect();
      menu.style.left = `${Math.min(innerWidth - 140, r.left - 40)}px`;
      menu.style.top = `${r.bottom + 4}px`;
      menu.innerHTML = `<div class="reason">${escapeHtml(reason || "Incertain")}</div>`;
      const keep = document.createElement("button"); keep.textContent = "Garder";
      const tom = document.createElement("button"); tom.textContent = "Tomate !";
      keep.onclick = (ev) => { ev.stopPropagation(); menu.remove(); host.remove(); this.bubble(pick(BUBBLES.keep), 1500); hooks.onKeep?.(card); };
      tom.onclick = (ev) => { ev.stopPropagation(); menu.remove(); hooks.onTomato?.(card); };
      menu.append(keep, tom);
      sh.appendChild(menu);
      const close = (ev: Event) => { if (!menu.contains(ev.target as Node)) { menu.remove(); document.removeEventListener("click", close, true); } };
      document.addEventListener("click", close, true);
    });
  }

  /* ---------------- throwing ---------------- */
  enqueue(req: ThrowRequest) { this.queue.push(req); void this.pump(); }

  private inFlight = 0;

  private async pump() {
    if (this.throwing) return;
    this.throwing = true;
    while (this.queue.length || this.inFlight) {
      if (!this.queue.length || this.inFlight >= 3) { await this.wait(120); continue; }
      const req = this.queue.shift()!;
      const rafale = this.queue.length > 2;
      this.inFlight++;
      this.spot(req.card);
      void (async () => {
        try {
          const done = await this.throwAt(req.card, req.reason, req.videoId, rafale);
          if (!done && (req.retries ?? 0) < 4) {
            req.retries = (req.retries ?? 0) + 1;
            this.queue.push(req); // covered/offscreen -> back of the queue
          }
        } finally { this.inFlight--; }
      })();
      await this.wait(rafale ? 450 : 700);
    }
    this.throwing = false;
    if (this.pendingClassify === 0) this.celebrate();
  }

  hand(): { x: number; y: number } {
    const r = this.char.getBoundingClientRect();
    const left = r.left + r.width * 0.86;
    return { x: this._pos.left ? r.left + r.width * 0.14 : left, y: r.top + r.height * 0.44 };
  }

  private covered(card: Element, r: DOMRect): boolean {
    const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!(el && !card.contains(el) && el !== card);
  }

  async throwAt(card: Element, reason: string, videoId = "", rafale = false): Promise<boolean> {
    let r = card.getBoundingClientRect();
    // covered by a modal or offscreen -> caller requeues to the end
    if ((r.height && this.covered(card, r)) || r.bottom < 0 || r.top > innerHeight * 1.5) {
      if (r.bottom < 0 || r.top > innerHeight * 1.5) {
        (card as HTMLElement).scrollIntoView({ behavior: this.reduced ? "auto" : "smooth", block: "center" });
        await this.wait(this.reduced ? 60 : 400);
        r = card.getBoundingClientRect();
      }
      if ((r.height && this.covered(card, r)) || r.bottom < 0 || r.top > innerHeight * 1.5) return false;
    }
    if (r.bottom < 0 || r.top > innerHeight) {
      (card as HTMLElement).scrollIntoView({ behavior: this.reduced ? "auto" : "smooth", block: "center" });
      await this.wait(this.reduced ? 60 : 550);
      r = card.getBoundingClientRect();
    }
    const tx = r.left + r.width / 2, ty = r.top + r.height / 2;
    const { x: sx, y: sy } = this.hand();
    const arm = this.part(".c-arm-r"), body = this.part(".c-body-all"), held = this.char.querySelector(".c-held") as SVGCircleElement;
    if (!this.reduced) {
      const wind = rafale ? 90 : 180, flight = rafale ? 480 : 620;
      // anticipation: lean back + wind-up
      await Promise.all([
        arm?.animate([{ transform: "rotate(0)" }, { transform: "rotate(-58deg)" }], { duration: wind, fill: "forwards", easing: "ease-out" }).finished,
        body?.animate([{ transform: "rotate(0)" }, { transform: "rotate(-4deg)" }], { duration: wind, fill: "forwards" }).finished,
      ]);
      // release: snap forward + squash
      arm?.animate([{ transform: "rotate(-58deg)" }, { transform: "rotate(18deg)" }], { duration: 140, fill: "forwards", easing: "ease-in" });
      body?.animate([{ transform: "rotate(-4deg) scaleY(1)" }, { transform: "rotate(2deg) scaleY(.94)" }], { duration: 140, fill: "forwards" });
      held?.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 60, fill: "forwards" });
      // tomato flight — parabola with spin + scale at apex + shadow
      const el = document.createElement("div");
      el.innerHTML = TOMATO_SVG(28);
      const t = el.firstElementChild as HTMLElement;
      t.style.left = "0"; t.style.top = "0";
      const shadow = document.createElement("div");
      shadow.className = "tshadow";
      this.root.querySelector(".wrap")!.append(shadow, t);
      const dist = Math.hypot(tx - sx, ty - sy);
      const apex = Math.min(170, dist * 0.38);
      const kfs: Keyframe[] = [], skfs: Keyframe[] = [];
      for (let i = 0; i <= 22; i++) {
        const p = i / 22;
        const x = sx + (tx - sx) * p;
        const y = sy + (ty - sy) * p - apex * 4 * p * (1 - p);
        const sc = 1 + Math.sin(p * Math.PI) * 0.35;
        kfs.push({ transform: `translate(${x - 14}px, ${y - 14}px) rotate(${p * 600}deg) scale(${sc})` });
        skfs.push({ transform: `translate(${x - 10}px, ${ty + 8}px) scale(${0.4 + p * 0.8})`, opacity: 0.3 + p * 0.5 });
      }
      const dur = flight + Math.min(220, dist / 5);
      const fly = t.animate(kfs, { duration: dur, easing: "cubic-bezier(.2,.75,.35,1)" });
      shadow.animate(skfs, { duration: dur, easing: "linear" });
      await fly.finished;
      t.remove(); shadow.remove();
      arm?.animate([{ transform: "rotate(18deg)" }, { transform: "rotate(0)" }], { duration: 320, fill: "forwards", easing: SPRING });
      this.setMouth("smirk");
      body?.animate([{ transform: "rotate(2deg) scaleY(.94)" }, { transform: "rotate(0) scaleY(1)" }], { duration: 260, fill: "forwards", easing: "ease-out" });
      held?.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 300, fill: "forwards", delay: 500 });
      // smirk / fist pump
      this.part(".c-arm-l")?.animate([{ transform: "rotate(0)" }, { transform: "rotate(-40deg)" }, { transform: "rotate(0)" }], { duration: 400 });
    }
    this.splat(reason, card, videoId);
    await this.hideCard(card);
    this.stripFor(card, reason, videoId);
    return true;
  }

  splat(reason: string, card: Element, videoId: string) {
    const s = document.createElement("div");
    s.className = "splat";
    s.innerHTML = splatSvg(Math.floor(Math.random() * 1e9)) +
      `<div class="reason">${escapeHtml(reason)} <span class="undo">Pardon ?</span></div>`;
    s.title = "Cliquer pour annuler";
    this.root.querySelector(".wrap")!.appendChild(s);
    // track the card's live rect so the splat never lands on a reflowed card
    const track = () => {
      if (!s.isConnected) return;
      const rr = card.getBoundingClientRect();
      if (rr.width === 0 || (card as HTMLElement).dataset.tomateHidden) { s.remove(); return; }
      s.style.left = `${rr.left + rr.width / 2}px`;
      s.style.top = `${rr.top + rr.height / 2}px`;
      requestAnimationFrame(track);
    };
    track();
    const ir = card.getBoundingClientRect();
    const x = ir.left + ir.width / 2, y = ir.top + ir.height / 2;
    if (!this.reduced) {
      for (let i = 0; i < 8; i++) {
        const p = document.createElement("div");
        p.className = "particle";
        p.style.left = `${x}px`; p.style.top = `${y}px`;
        p.style.background = i % 3 ? "#d63031" : "#e74c3c";
        this.root.querySelector(".wrap")!.appendChild(p);
        const a = Math.random() * Math.PI * 2, d = 30 + Math.random() * 45;
        p.animate([
          { transform: "translate(0,0)", opacity: 1 },
          { transform: `translate(${Math.cos(a) * d}px, ${Math.sin(a) * d * .6 + 34}px)`, opacity: 0 },
        ], { duration: 550 + Math.random() * 250, easing: "cubic-bezier(.2,.6,.4,1)" }).finished.then(() => p.remove());
      }
    }
    const timer = setTimeout(() => s.remove(), 3200);
    s.addEventListener("click", () => {
      clearTimeout(timer); s.remove();
      this.restore(card);
      this.bubble(pick(BUBBLES.undo), 1400);
      this.onUndo(card, videoId);
    });
  }

  async hideCard(card: Element) {
    const el = card as HTMLElement;
    el.dataset.tomateHidden = "1";
    if (!this.reduced) {
      await el.animate([
        { transform: "translateX(0) rotate(0)", opacity: 1 },
        { transform: "translateX(-7px)", offset: .2 },
        { transform: "translateX(7px)", offset: .4 },
        { transform: "translateX(0)", offset: .55 },
        { transform: "rotate(-2.5deg) translateY(26px) scale(.95)", opacity: 0 },
      ], { duration: 500, easing: "ease-in" }).finished.catch(() => {});
    }
    el.style.transition = "none";
    el.style.display = "none";
  }

  // slim in-flow placeholder left where the card was, with undo
  stripFor(card: Element, reason: string, videoId: string) {
    const el = card as HTMLElement;
    const host = document.createElement("div");
    host.className = "tomate-strip-host";
    const sh = host.attachShadow({ mode: "open" });
    const st = document.createElement("style");
    st.textContent = CSS;
    sh.appendChild(st);
    const strip = document.createElement("div");
    strip.className = "strip";
    strip.innerHTML = `${TOMATO_SVG(16)}<span>Tomatée : ${escapeHtml(reason || "hors sujet")}</span><span class="undo">Pardon ?</span>`;
    strip.title = "Cliquer pour annuler";
    sh.appendChild(strip);
    el.parentElement?.insertBefore(host, el.nextSibling);
    strip.addEventListener("click", () => {
      host.remove();
      this.restore(el);
      this.bubble(pick(BUBBLES.undo), 1400);
      this.onUndo(el, videoId);
    });
    setTimeout(() => {
      strip.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 400, fill: "forwards" })
        .finished.then(() => {
          host.animate([{ height: "28px" }, { height: "0px", opacity: 0 }], { duration: 250, fill: "forwards", easing: "ease-out" })
            .finished.then(() => host.remove());
        });
    }, 4000);
  }

  restore(card: Element) {
    const el = card as HTMLElement;
    delete el.dataset.tomateHidden;
    el.style.display = "";
    if (!this.reduced) el.animate([{ opacity: 0, transform: "rotate(-2deg)" }, { opacity: 1, transform: "rotate(0)" }], { duration: 300 });
  }

  /* ---------------- user throw mode ---------------- */
  private cursorTom: HTMLElement | null = null;

  toggleThrowMode() {
    this.throwMode = !this.throwMode;
    document.body.dataset.tomateThrow = this.throwMode ? "1" : "";
    document.body.style.cursor = this.throwMode ? "none" : "";
    if (this.throwMode && !this.reduced) {
      this.cursorTom = document.createElement("div");
      this.cursorTom.className = "cursor-tomato";
      this.cursorTom.innerHTML = TOMATO_SVG(30);
      this.root.querySelector(".wrap")!.appendChild(this.cursorTom);
    } else { this.cursorTom?.remove(); this.cursorTom = null; }
    this.bubble(this.throwMode ? "Clique sur une vidéo !" : "OK, je range les tomates.", 1800);
  }

  bindThrowMode(getCardAt: (el: Element) => Element | null) {
    document.addEventListener("mousemove", (e) => {
      if (this.cursorTom) {
        this.cursorTom.style.transform = `translate(${e.clientX - 15}px, ${e.clientY - 15}px) rotate(${Math.sin(e.clientX / 30) * 14}deg)`;
      }
    }, true);
    document.addEventListener("mouseover", (e) => {
      if (!this.throwMode) return;
      document.querySelectorAll(".fx-highlight").forEach((c) => { c.classList.remove("fx-highlight"); c.querySelector(":scope > .reticle")?.remove(); });
      const card = getCardAt(e.target as Element);
      if (card) {
        card.classList.add("fx-highlight");
        const el = card as HTMLElement;
        if (getComputedStyle(el).position === "static") el.style.position = "relative";
        const ret = document.createElement("div");
        ret.className = "reticle";
        el.appendChild(ret);
      }
    }, true);
    document.addEventListener("click", (e) => {
      if (!this.throwMode) return;
      const card = getCardAt(e.target as Element);
      if (!card) return;
      e.preventDefault(); e.stopPropagation();
      this.toggleThrowMode();
      // little clap
      this.part(".c-arm-l")?.animate([{ transform: "rotate(0)" }, { transform: "rotate(-50deg)" }, { transform: "rotate(0)" }], { duration: 300, iterations: 2 });
      this.onManualThrow(card);
    }, true);
    document.addEventListener("keydown", (e) => {
      const typing = /^(input|textarea|select)$/i.test((e.target as HTMLElement).tagName)
        || (e.target as HTMLElement).isContentEditable;
      if (e.key === "Escape" && this.throwMode) this.toggleThrowMode();
      if ((e.key === "t" || e.key === "T") && !typing) this.toggleThrowMode();
    });
  }

  wait(ms: number) { return new Promise((r) => setTimeout(r, ms)); }
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}
