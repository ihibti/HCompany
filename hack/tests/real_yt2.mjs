import { chromium } from 'playwright';
import path from 'node:path';
const EXT = path.resolve('../extension/dist');
const ctx = await chromium.launchPersistentContext('/tmp/tomate-real4', {
  headless: false,
  args: ['--headless=new', `--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
  viewport: { width: 1400, height: 900 },
  recordVideo: { dir: '/tmp/tomate-videos', size: { width: 1400, height: 900 } },
});
let sw = ctx.serviceWorkers()[0];
if (!sw) sw = await ctx.waitForEvent('serviceworker', { timeout: 10000 });
await sw.evaluate(() => chrome.storage.local.set({ backendUrl: 'http://localhost:8787', autoThrow: true }));
const prof = await (await fetch('http://localhost:8787/profile', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: "Je veux voir de l'escalade, des chiens et de la cuisine japonaise, pas de drama ni de gaming" }) })).json();
console.log('profile', prof.id);
await sw.evaluate((pid) => chrome.storage.local.set({ profileId: pid }), prof.id);
const page = await ctx.newPage();
await page.goto('https://www.youtube.com/results?search_query=fortnite+ramen+drama', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(3000);
for (const sel of [page.getByRole('button', { name: /Tout refuser/i }), page.getByRole('button', { name: /Reject all/i })]) {
  if (await sel.count()) { await sel.click().catch(()=>{}); break; }
}
await page.waitForTimeout(1500);
const t0 = Date.now();
let firstVeil = 0, allHidden = 0;
for (let i = 0; i < 60; i++) {
  await page.waitForTimeout(1000);
  const s = await page.evaluate(() => ({
    tiles: document.querySelectorAll('ytd-video-renderer, ytd-rich-item-renderer, yt-lockup-view-model, ytm-shorts-lockup-view-model, ytm-shorts-lockup-view-model-v2, grid-shelf-view-model').length,
    veils: document.querySelectorAll('.tomate-veil-host').length,
    hidden: [...document.querySelectorAll('ytd-video-renderer, ytd-rich-item-renderer, yt-lockup-view-model, ytm-shorts-lockup-view-model, grid-shelf-view-model')].filter(e => getComputedStyle(e).display==='none' || e.dataset.tomateHidden).length,
    repl: document.querySelectorAll('.tomate-replacement').length,
  }));
  if (!firstVeil && s.veils) { firstVeil = Date.now() - t0; }
  if (i % 5 === 0 || s.hidden) console.log(((Date.now()-t0)/1000).toFixed(1)+'s', JSON.stringify(s));
  if (s.hidden > 0 && !s.veils) { allHidden = Date.now() - t0; break; }
}
// scroll 3x
for (let i = 0; i < 3; i++) {
  await page.evaluate(() => scrollBy(0, 1400));
  await page.waitForTimeout(2500);
  const s = await page.evaluate(() => ({
    tiles: document.querySelectorAll('ytd-video-renderer, ytd-rich-item-renderer, yt-lockup-view-model').length,
    veils: document.querySelectorAll('.tomate-veil-host').length,
    hidden: [...document.querySelectorAll('ytd-video-renderer, ytd-rich-item-renderer, yt-lockup-view-model')].filter(e => getComputedStyle(e).display==='none' || e.dataset.tomateHidden).length,
    repl: document.querySelectorAll('.tomate-replacement').length,
  }));
  console.log('scroll'+(i+1), JSON.stringify(s));
}
await page.screenshot({ path: '/tmp/tomate-shots/yt-real-v2.png' });
console.log('firstVeil', firstVeil, 'allHidden', allHidden);
await ctx.close();
