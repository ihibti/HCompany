// Real YouTube home: "Ton feed Tomate" shelf + "Remplacer tout l'accueil".
// Needs backend on BACKEND (default real :8787) and a prod build in ../extension/dist.
import { chromium } from 'playwright';
import { execSync } from 'node:child_process';
import path from 'node:path';

const EXT = path.resolve('../extension/dist');
const BACKEND = process.env.BACKEND || 'http://localhost:8787';
const SHOTS = '/tmp/tomate-shots';
execSync('mkdir -p ' + SHOTS);

const ctx = await chromium.launchPersistentContext('/tmp/tomate-home', {
  headless: false,
  args: ['--headless=new', `--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`, '--lang=fr-FR'],
  viewport: { width: 1400, height: 900 },
  locale: 'fr-FR',
});
let sw = ctx.serviceWorkers()[0];
if (!sw) sw = await ctx.waitForEvent('serviceworker', { timeout: 10000 });
const prof = await (await fetch(BACKEND + '/profile', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ text: "Je veux voir de l'escalade et de la cuisine japonaise, pas de drama ni de gaming" }),
})).json();
console.log('profile', prof.id, prof.include?.map((t) => t.topic));
await sw.evaluate(([p, b]) => chrome.storage.local.set({ backendUrl: b, profileId: p.id, profile: p, autoThrow: true, replaceHome: false }), [prof, BACKEND]);

const page = await ctx.newPage();
page.on('console', (m) => { if (/tomate/i.test(m.text())) console.log('[page]', m.text()); });
await page.goto('https://www.youtube.com/', { waitUntil: 'domcontentloaded' });
const reject = page.getByRole('button', { name: /Tout refuser|Reject all/i }).first();
await reject.waitFor({ timeout: 8000 }).then(() => reject.click()).catch(() => {});

const shelfState = () => page.evaluate(() => {
  const host = document.querySelector('.tomate-shelf');
  const cards = host?.shadowRoot?.querySelectorAll('.tomate-replacement') ?? [];
  const grid = document.querySelector('ytd-browse[page-subtype="home"] ytd-rich-grid-renderer');
  return {
    path: location.pathname,
    shelf: !!host, visible: !!host && host.getBoundingClientRect().height > 0,
    cards: cards.length, titles: [...cards].slice(0, 10).map((c) => c.shadowRoot?.querySelector('.t')?.textContent?.slice(0, 50)),
    thumbs: [...cards].filter((c) => c.shadowRoot?.querySelector('img')?.src).length, status: host?.shadowRoot?.querySelector('.st')?.textContent ?? '',
    gridHidden: grid ? getComputedStyle(grid).display === 'none' : null,
  };
});

let s;
for (let i = 0; i < 45; i++) {
  await page.waitForTimeout(1000);
  s = await shelfState();
  if (i % 5 === 0) console.log(`${i}s`, JSON.stringify(s));
  if (s.cards >= 4) break;
}
console.log('home', JSON.stringify(s));
await page.screenshot({ path: SHOTS + '/yt-home-shelf.png' });

// replace-home mode
await sw.evaluate(() => chrome.storage.local.set({ replaceHome: true }));
await page.waitForTimeout(1500);
console.log('replaceHome', JSON.stringify(await shelfState()));
await page.screenshot({ path: SHOTS + '/yt-home-replaced.png' });

// SPA nav away and back: shelf must leave /watch alone and come back on home
await page.goto('https://www.youtube.com/results?search_query=escalade', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2000);
await page.evaluate(() => (document.querySelector('a#logo, ytd-topbar-logo-renderer a'))?.click());
await page.waitForTimeout(4000);
console.log('back home (SPA)', JSON.stringify(await shelfState()));
await page.screenshot({ path: SHOTS + '/yt-home-spa.png' });
await ctx.close();
