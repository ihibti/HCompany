import { chromium } from 'playwright';
import path from 'node:path';
const EXT = path.resolve('../extension/dist');
const ctx = await chromium.launchPersistentContext('/tmp/tomate-real3', {
  headless: false,
  args: ['--headless=new', `--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
  viewport: { width: 1400, height: 900 },
  recordVideo: { dir: '/tmp/tomate-videos', size: { width: 1400, height: 900 } },
});
let sw = ctx.serviceWorkers()[0];
if (!sw) sw = await ctx.waitForEvent('serviceworker', { timeout: 10000 });
await sw.evaluate(() => chrome.storage.local.set({ backendUrl: 'http://localhost:8788' }));
const prof = await (await fetch('http://localhost:8788/profile', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: "Je veux voir de l'escalade et de la cuisine japonaise, pas de drama ni de gaming" }) })).json();
console.log('profile', prof.id);
await sw.evaluate((pid) => chrome.storage.local.set({ profileId: pid, autoThrow: true }), prof.id);
const page = await ctx.newPage();
page.on('pageerror', e => console.log('[err]', e.message));
page.on('console', m => { if (m.type()==='error') console.log('[pg]', m.text().slice(0,160)); });
await page.goto('https://www.youtube.com/results?search_query=ramen+recette+fortnite', { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(4000);
// refuse cookies and WAIT for the dialog to be gone
const refuse = page.getByRole('button', { name: /Tout refuser|Reject all/i }).first();
for (const sel of [page.getByRole('button', { name: /Tout refuser/i }), page.getByRole('button', { name: /Reject all/i }), page.locator('button:has-text("Tout refuser")')]) {
  if (await sel.count()) { await sel.click().catch(()=>{}); break; }
}
await page.waitForTimeout(1500);
console.log('dialog visible:', await page.locator('tp-yt-paper-dialog, [role="dialog"], ytd-consent-bump-v2-lightbox').first().isVisible().catch(() => false));
await page.waitForTimeout(20000);
const stats = await page.evaluate(() => ({
  ...(window.__tomateStats ?? {}),
  tiles: document.querySelectorAll('ytd-rich-item-renderer, ytd-video-renderer, ytd-compact-video-renderer, yt-lockup-view-model, ytm-shorts-lockup-view-model, ytm-shorts-lockup-view-model-v2, grid-shelf-view-model').length,
  hidden: [...document.querySelectorAll('ytd-rich-item-renderer, ytd-video-renderer, ytd-compact-video-renderer, yt-lockup-view-model')].filter(e => getComputedStyle(e).display === 'none').length,
  sel: {
    rich: document.querySelectorAll('ytd-rich-item-renderer').length,
    video: document.querySelectorAll('ytd-video-renderer').length,
    compact: document.querySelectorAll('ytd-compact-video-renderer').length,
    lockup: document.querySelectorAll('yt-lockup-view-model').length,
    shorts1: document.querySelectorAll('ytm-shorts-lockup-view-model').length,
    shorts2: document.querySelectorAll('ytm-shorts-lockup-view-model-v2').length,
    shelf: document.querySelectorAll('grid-shelf-view-model').length,
  },
}));
console.log(JSON.stringify(stats, null, 1));
await page.screenshot({ path: '/tmp/tomate-shots/youtube-real-pass.png' });
await ctx.close();
