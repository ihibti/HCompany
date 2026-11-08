import { chromium } from 'playwright';
import path from 'node:path';
const EXT = path.resolve('../extension/dist');
const ctx = await chromium.launchPersistentContext('/tmp/tomate-vid', {
  headless: false,
  args: ['--headless=new', `--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
  viewport: { width: 1400, height: 900 },
  recordVideo: { dir: '/tmp/tomate-videos2', size: { width: 1400, height: 900 } },
});
let sw = ctx.serviceWorkers()[0] || await ctx.waitForEvent('serviceworker');
const prof = await (await fetch('http://localhost:8790/profile', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text:'escalade cuisine, pas drama gaming'}) })).json();
await sw.evaluate((pid) => chrome.storage.local.set({ profileId: pid, autoThrow: true, backendUrl:'http://localhost:8790' }), prof.id);
const page = await ctx.newPage();
await page.goto('http://localhost:8899/youtube_dense.html');
await page.waitForTimeout(14000); // rafale over ~16 off cards
await ctx.close();

const ctx2 = await chromium.launchPersistentContext('/tmp/tomate-vid2', {
  headless: false,
  args: ['--headless=new', `--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
  viewport: { width: 1400, height: 900 },
  recordVideo: { dir: '/tmp/tomate-videos2', size: { width: 1400, height: 900 } },
});
sw = ctx2.serviceWorkers()[0] || await ctx2.waitForEvent('serviceworker');
await sw.evaluate((pid) => chrome.storage.local.set({ profileId: pid, autoThrow: false, backendUrl:'http://localhost:8790' }), prof.id);
const p2 = await ctx2.newPage();
await p2.goto('http://localhost:8899/youtube.html');
await p2.waitForTimeout(2000);
await p2.keyboard.press('t');
await p2.waitForTimeout(600);
await p2.locator('ytd-rich-item-renderer:not([data-tomate-hidden])').first().click({position:{x:150,y:40}});
await p2.waitForTimeout(2500);
await ctx2.close();
console.log('vids done');
