// Сквозная проверка prod-сборки: форма → api/send.php → заглушка Telegram.
// Запускается из scripts/qa/e2e_prod.sh, который поднимает php -S и заглушку.
const { chromium } = require('playwright');
const base = process.argv[2] || 'http://127.0.0.1:8080/';
let failed = 0;
const ok = (c, m) => { console.log(`${c ? 'OK  ' : 'FAIL'} ${m}`); if (!c) failed++; };

async function fill(page) {
  await page.fill('#f-name', 'Мария');
  await page.fill('#f-car', 'Skoda Octavia');
  await page.selectOption('#f-year-from', '2020');
  await page.selectOption('#f-year-to', '2023');
  await page.fill('#f-contact', '@maria_test');
  await page.check('#f-consent', { force: true });
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.goto(base, { waitUntil: 'networkidle' });
  ok(await page.$eval('#lead-form', (f) => f.dataset.mode) === 'live', 'prod: форма в боевом режиме');
  await page.waitForTimeout(3200); // быстрее 3 с сервер молча отсечёт как бота
  await fill(page);
  const [resp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('api/send.php')),
    page.click('.form__button'),
  ]);
  const body = await resp.json();
  ok(resp.status() === 200 && body.ok && body.id > 1000, `fetch → 200 ${JSON.stringify(body)}`);
  await page.waitForSelector('#form-done:not([hidden])');
  ok(true, 'панель успеха показана');
  ok(await page.$('#form-done .done__link') === null, 'без telegram_catalog_url кнопки каталога нет');

  const nojs = await browser.newPage({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  await nojs.goto(base);
  await fill(nojs);
  await Promise.all([nojs.waitForNavigation(), nojs.click('.form__button')]);
  ok(nojs.url().endsWith('/spasibo/'), `без JS: редирект на spasibo/ (${nojs.url()})`);
  ok((await nojs.textContent('h1')).includes('Спасибо'), 'страница «спасибо» открылась');

  await browser.close();
  console.log(failed ? `\nПровалено: ${failed}` : '\nВсе проверки пройдены');
  process.exit(failed ? 1 : 0);
})();
