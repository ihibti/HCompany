import { chromium } from 'playwright';
import path from 'node:path';
const EXT = path.resolve('../extension/dist');
const ctx = await chromium.launchPersistentContext('/tmp/tomate-profile', {
  headless: false,
  args: ['--headless=new', `--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
});
const page = await ctx.newPage();
await page.goto('http://localhost:8899/tiktok.html');
await page.waitForTimeout(2000);
await page.locator('body').click({position:{x:10,y:10}});
await page.keyboard.press('t');
await page.waitForTimeout(400);
await page.locator('[data-e2e="recommend-list-item-container"]').first().click({ position: { x: 100, y: 30 } });
await page.waitForTimeout(3000);
const disp = await page.evaluate(() => getComputedStyle(document.querySelector('[data-e2e="recommend-list-item-container"]')).display);
console.log('throwmode:', await page.evaluate(() => document.body.dataset.tomateThrow));
const sw = ctx.serviceWorkers()[0];
const counters = await sw.evaluate(() => chrome.storage.local.get("counters"));
console.log('display:', disp, 'counters:', JSON.stringify(counters));
await ctx.close();
