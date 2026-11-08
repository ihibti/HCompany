import { chromium } from 'playwright';
import path from 'node:path';
const EXT = path.resolve('../extension/dist');
const shots = '/tmp/tomate-frames';
import { execSync } from 'node:child_process'; execSync('mkdir -p ' + shots);
for (const dark of [false, true]) {
  const ctx = await chromium.launchPersistentContext('/tmp/tomate-fr' + dark, {
    headless: false, colorScheme: dark ? 'dark' : 'light',
    deviceScaleFactor: 3,
    args: ['--headless=new', `--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
    viewport: { width: 800, height: 600 },
  });
  let sw = ctx.serviceWorkers()[0] || await ctx.waitForEvent('serviceworker');
  const page = await ctx.newPage();
  await page.goto('http://localhost:8899/harness.html');
  await page.waitForTimeout(1000);
  const tag = dark ? 'dark' : 'light';
  await page.evaluate((d) => window.__tomateDebug.setTheme(d ? 'dark' : 'light'), dark);
  await page.evaluate(() => window.__tomateDebug.wake());
  const clip = { x: 520, y: 340, width: 280, height: 260 };
  const shot = (n) => page.screenshot({ path: `${shots}/char-${n}-${tag}.png`, clip });
  // idle (profile set => awake)
  await page.waitForTimeout(600); await shot('idle');
  // sleep
  await page.evaluate(() => window.__tomateDebug.sleep());
  await page.waitForTimeout(400); await shot('sleep');
  await page.evaluate(() => window.__tomateDebug.wake());
  // aim
  await page.evaluate(() => window.__tomateDebug.aim());
  await page.waitForTimeout(350); await shot('aim');
  // throw: start, then pause animations at exact phases
  await page.evaluate(() => window.__tomateDebug.throwAt());
  await page.waitForTimeout(120);                      // mid wind-up
  await page.evaluate(() => window.__tomateDebug.pauseAt(150));
  await shot('windup');
  await page.evaluate(() => window.__tomateDebug.play());
  await page.waitForTimeout(160);                      // release snap
  await page.evaluate(() => window.__tomateDebug.pauseAt(320));
  await shot('release');
  await page.evaluate(() => window.__tomateDebug.play());
  await page.waitForTimeout(380);                      // tomato mid-flight apex
  await page.evaluate(() => window.__tomateDebug.pauseAt(900));
  const wide = { x: 250, y: 120, width: 550, height: 480 };
  await page.screenshot({ path: `${shots}/char-apex-${tag}.png`, clip: wide });
  await page.evaluate(() => window.__tomateDebug.play());
  await page.waitForTimeout(700);                      // impact+splat visible
  await page.evaluate(() => window.__tomateDebug.pauseAt(200));
  await page.screenshot({ path: `${shots}/char-impact-${tag}.png`, clip: wide });
  await page.evaluate(() => window.__tomateDebug.play());
  // celebrate mid-jump
  await page.waitForTimeout(600);
  await page.evaluate(() => window.__tomateDebug.celebrate());
  await page.waitForTimeout(200);
  await page.evaluate(() => window.__tomateDebug.pauseAt(220));
  await shot('celebrate');
  await ctx.close();
}
console.log('frames done');
