// Скриншоты для QA: node scripts/qa/screens.js [url] [папка]
// Playwright с Chromium должен быть установлен (в облачной среде он предустановлен).
const { chromium } = require('playwright');

const url = process.argv[2] || 'http://localhost:8000/';
const out = process.argv[3] || 'qa';
const sizes = [[360, 780], [390, 844], [768, 1024], [1440, 900]];

(async () => {
  const browser = await chromium.launch();
  for (const [w, h] of sizes) {
    const mobile = w < 768;
    const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile });
    const external = [];
    page.on('request', (r) => { if (!r.url().startsWith(new URL(url).origin)) external.push(r.url()); });
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    // прокрутка до конца, чтобы подгрузились картинки с loading="lazy"
    await page.evaluate(async () => {
      for (let y = 0; y < document.body.scrollHeight; y += 600) { window.scrollTo({ top: y, behavior: 'instant' }); await new Promise((r) => setTimeout(r, 40)); }
      window.scrollTo({ top: 0, behavior: 'instant' });
    });
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${out}/${w}-fold.png` });
    await page.screenshot({ path: `${out}/${w}.png`, fullPage: true });
    const cta = await page.$('.hero__cta');
    const box = cta ? await cta.boundingBox() : null;
    const scrollW = await page.evaluate(() => document.documentElement.scrollWidth);
    console.log(`${w}×${h}: кнопка первого экрана ${box ? `низ ${Math.round(box.y + box.height)}px` : 'не найдена'}` +
      `${box && box.y + box.height <= h ? ' — видна без прокрутки' : ' — НЕ видна'}; ширина документа ${scrollW}px` +
      `${external.length ? `; ВНЕШНИЕ ЗАПРОСЫ: ${external.join(', ')}` : '; внешних запросов нет'}`);
    await page.close();
  }
  await browser.close();
})();
