// E2E: extension + fixtures + backend FAKE_AI=1
import { chromium } from 'playwright';
import { execSync } from 'node:child_process';
import path from 'node:path';

const EXT = path.resolve('../extension/dist');
const FIXTURE = 'http://localhost:8899';
const BACKEND = 'http://localhost:8790';
const SHOTS = '/tmp/tomate-shots';
execSync('mkdir -p ' + SHOTS);

// seed a profile in the fake backend
const prof = await (await fetch(BACKEND + '/profile', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ text: 'escalade et cuisine japonaise, pas de drama ni gaming' }),
})).json();
console.log('profile', prof.id);

const ctx = await chromium.launchPersistentContext('/tmp/tomate-profile', {
  headless: false,
  args: ['--headless=new', `--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
  viewport: { width: 1400, height: 900 },
  recordVideo: { dir: '/tmp/tomate-videos', size: { width: 1400, height: 900 } },
});

// set profileId + autothrow in extension storage via a fixture page's content script context:
// simplest: service worker can't set content storage; use storage via an extension page (panel).
let sw = ctx.serviceWorkers()[0];
if (!sw) sw = await ctx.waitForEvent('serviceworker', { timeout: 10000 });
await sw.evaluate((pid) => chrome.storage.local.set({ profileId: pid, autoThrow: true, enabled: { youtube: true, tiktok: true, instagram: true } }), prof.id);
console.log('storage set via SW');

const page = await ctx.newPage();
const results = {};
for (const p of ['youtube', 'tiktok', 'instagram']) {
  await page.goto(`${FIXTURE}/${p}.html`, { waitUntil: 'domcontentloaded' });
  // capture mid-throw frames while the pass runs
  const snapAt = [800, 1500, 2200, 3000, 4000, 5000];
  for (const t of snapAt) {
    await page.waitForTimeout(t === 800 ? 800 : 700);
    await page.screenshot({ path: `${SHOTS}/${p}-frame${t}.png` });
  }
  await page.waitForTimeout(4000);
  const hiddenCount = await page.evaluate(() =>
    [...document.querySelectorAll('ytd-rich-item-renderer, [data-e2e="recommend-list-item-container"], [data-e2e="explore-item"], article')].filter(e => getComputedStyle(e).display === 'none').length);
  const q = await page.evaluate(() => document.querySelectorAll('.badge-q').length);
  // assertion: no splat/tooltip intersects a visible on-topic card
  const splatOverlap = await page.evaluate(() => {
    const host = document.getElementById('tomate-overlay-host');
    const splats = host?.shadowRoot ? [...host.shadowRoot.querySelectorAll('.splat')] : [];
    const cards = [...document.querySelectorAll('ytd-rich-item-renderer, [data-e2e="recommend-list-item-container"], [data-e2e="explore-item"], article')]
      .filter(c => getComputedStyle(c).display !== 'none' && !c.dataset.tomateHidden);
    let bad = 0;
    for (const sp of splats) {
      const r = sp.getBoundingClientRect();
      for (const c of cards) {
        const cr = c.getBoundingClientRect();
        if (r.left < cr.right && r.right > cr.left && r.top < cr.bottom && r.bottom > cr.top) bad++;
      }
    }
    return bad;
  });
  results[p] = { hidden: hiddenCount, unsure: q, splatOverlap };
  await page.screenshot({ path: `${SHOTS}/${p}-after.png` });
}

// undo: click a lingering splat if any (shadow dom — use position)
await page.goto(`${FIXTURE}/tiktok.html`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3000);
const box = await page.evaluate(() => {
  const host = document.getElementById('tomate-overlay-host');
  const s = host?.shadowRoot?.querySelector('.splat');
  if (!s) return null;
  const r = s.getBoundingClientRect();
  return { x: r.left + r.width/2, y: r.top + r.height/2 };
});
if (box) {
  await page.mouse.click(box.x, box.y);
  await page.waitForTimeout(600);
  results.undo = await page.evaluate(() => [...document.querySelectorAll('[data-e2e]')].some(e => getComputedStyle(e).display !== 'none'));
} else results.undo = 'no-splat';
await page.screenshot({ path: `${SHOTS}/undo.png` });

// user throw mode on youtube: re-show, press T, click a card
await page.goto(`${FIXTURE}/youtube.html`, { waitUntil: 'domcontentloaded' });
await page.evaluate(() => chrome?.storage ? null : null);
await page.waitForTimeout(2500);
await page.keyboard.press('t');
await page.waitForTimeout(300);
const card = page.locator('ytd-rich-item-renderer:not([data-tomate-hidden])').first();
await card.click({ position: { x: 150, y: 40 } });
await page.waitForTimeout(1500);
results.manual = await page.evaluate(() => document.querySelector('ytd-rich-item-renderer') && getComputedStyle(document.querySelector('ytd-rich-item-renderer')).display);
await page.screenshot({ path: `${SHOTS}/manual-throw.png` });

console.log(JSON.stringify(results, null, 1));

// ---- dense fixture: speed, freshness, infinite scroll ----
await page.goto(`${FIXTURE}/youtube_dense.html`, { waitUntil: 'domcontentloaded' });
const t0 = Date.now();
await page.waitForTimeout(1500);
const veiled15 = await page.evaluate(() => document.querySelectorAll('.tomate-veil-host').length);
await page.waitForTimeout(6000);
const dense1 = await page.evaluate(() => ({
  hidden: [...document.querySelectorAll('ytd-rich-item-renderer')].filter(e => getComputedStyle(e).display === 'none' || e.dataset.tomateHidden).length,
  veils: document.querySelectorAll('.tomate-veil-host').length,
  stats: window.__tomateStats,
}));
console.log('veiled@1.5s:', veiled15, 'dense:', JSON.stringify(dense1));
await page.waitForTimeout(6000); // let recycle + dynamic cards process
const dense2 = await page.evaluate(() => {
  const cards = [...document.querySelectorAll('ytd-rich-item-renderer')];
  const byId = (vid) => cards.find(c => c.querySelector('a')?.href.includes(vid));
  return {
    recycledOnVisible: byId('recycled_on') ? getComputedStyle(byId('recycled_on')).display !== 'none' : null,
    recycledOffHidden: byId('recycled_off') ? getComputedStyle(byId('recycled_off')).display === 'none' || !!byId('recycled_off').dataset.tomateHidden : null,
    stats: window.__tomateStats,
  };
});
console.log('freshness:', JSON.stringify(dense2));
await page.screenshot({ path: `${SHOTS}/dense-final.png` });
await ctx.close();
