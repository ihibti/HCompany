import { chromium } from 'playwright';
import path from 'node:path';
const EXT = path.resolve('../extension/dist');
const ctx = await chromium.launchPersistentContext('/tmp/tomate-profile', {
  headless: false,
  args: ['--headless=new', `--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
});
const page = await ctx.newPage();
page.on('console', m => console.log('[pg]', m.type(), m.text().slice(0,220)));
page.on('pageerror', e => console.log('[err]', e.message));
await page.goto('http://localhost:8899/youtube.html');
await page.waitForTimeout(4000);
console.log(await page.evaluate(() => JSON.stringify({
  hidden: [...document.querySelectorAll('ytd-rich-item-renderer')].filter(e => getComputedStyle(e).display==='none').length,
})));
await ctx.close();
