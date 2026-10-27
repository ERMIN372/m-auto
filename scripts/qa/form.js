// Проверка формы, CTA и липкой кнопки: node scripts/qa/form.js [url]
const { chromium } = require('playwright');
const url = process.argv[2] || 'http://localhost:8000/';
let failed = 0;
const ok = (cond, msg) => { console.log(`${cond ? 'OK  ' : 'FAIL'} ${msg}`); if (!cond) failed++; };

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const logs = [];
  page.on('console', (m) => logs.push(m.text()));
  await page.goto(url + '?utm_source=yandex&utm_medium=cpc&utm_campaign=test&yclid=123', { waitUntil: 'networkidle' });

  const sticky = () => page.$eval('#sticky-cta', (el) => getComputedStyle(el).visibility === 'visible');
  ok(!(await sticky()), 'липкая кнопка скрыта на первом экране');

  const afterForm = () => page.evaluate(() => {
    const r = document.getElementById('form').getBoundingClientRect();
    window.scrollTo({ top: r.bottom + window.scrollY + 300, behavior: 'instant' });
  });
  await afterForm();
  await page.waitForTimeout(400);
  ok(await sticky(), 'липкая кнопка видна ниже формы');
  ok(await page.evaluate(() => getComputedStyle(document.body).paddingBottom) !== '0px', 'у страницы есть нижний отступ под липкую кнопку');

  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
  await page.waitForTimeout(300);
  await page.click('.hero__cta');
  await page.waitForTimeout(900);
  ok(await page.evaluate(() => document.activeElement.id) === 'f-name', 'кнопка первого экрана ставит фокус в «Имя»');
  const formTop = await page.$eval('#form', (el) => Math.round(el.getBoundingClientRect().top));
  ok(Math.abs(formTop) < 40, `форма прокручена к верху экрана (top=${formTop})`);
  ok(!(await sticky()), 'липкая кнопка скрыта, когда форма видна');

  // пустая отправка
  await page.click('.form__button');
  const errs = await page.$$eval('.field__error', (els) => els.filter((e) => e.textContent).map((e) => e.id));
  ok(errs.includes('f-name-error') && errs.includes('f-car-error') && errs.includes('f-years-error') && errs.includes('f-contact-error') && errs.includes('f-consent-error'),
    `ошибки при пустой отправке: ${errs.join(', ')}`);
  ok(await page.evaluate(() => document.activeElement.id) === 'f-name', 'фокус на первом поле с ошибкой');
  ok(await page.$eval('#f-name', (el) => el.getAttribute('aria-invalid')) === 'true', 'aria-invalid выставлен');

  await page.fill('#f-name', 'Алексей');
  ok(await page.$eval('#f-name-error', (e) => e.textContent) === '', 'ошибка имени ушла при вводе');
  await page.fill('#f-car', 'Volkswagen Tiguan');
  await page.selectOption('#f-year-from', '2022');
  await page.selectOption('#f-year-to', '2019');
  ok((await page.$eval('#f-years-error', (e) => e.textContent)).includes('не может быть раньше'), 'год «до» раньше «от» → ошибка');
  await page.selectOption('#f-year-to', '2024');
  ok(await page.$eval('#f-years-error', (e) => e.textContent) === '', 'ошибка годов ушла');

  await page.type('#f-mileage-from', '120000');
  ok(await page.$eval('#f-mileage-from', (e) => e.value) === '120 000', 'пробел между разрядами при вводе пробега');
  await page.type('#f-mileage-to', '80000');
  await page.click('#f-contact');
  ok((await page.$eval('#f-mileage-error', (e) => e.textContent)).includes('меньше'), 'пробег «до» меньше «от» → ошибка');
  await page.fill('#f-mileage-to', '');
  await page.type('#f-mileage-to', '150000');
  ok(await page.$eval('#f-mileage-error', (e) => e.textContent) === '', 'ошибка пробега ушла');

  await page.fill('#f-contact', '@ivan_petrov');
  await page.click('.choice__item:nth-child(2)');
  ok(await page.$eval('#f-contact-label', (e) => e.textContent) === 'Телефон для звонка', '«Позвонить» меняет подпись поля');
  ok((await page.$eval('#f-contact-error', (e) => e.textContent)).includes('номер телефона'), '«Позвонить» + ник → нужна ошибка про телефон');
  await page.fill('#f-contact', '8 (999) 123-45-67');
  ok(await page.$eval('#f-contact-error', (e) => e.textContent) === '', 'телефон принят');
  await page.click('.choice__item:nth-child(1)');

  await page.click('.form__button');
  ok(await page.evaluate(() => document.activeElement.id) === 'f-consent', 'без галочки не отправляется, фокус на галочке');
  await page.click('.check');
  await page.click('.form__button');
  await page.waitForTimeout(100);
  ok(await page.$eval('.form__button', (b) => b.disabled && b.textContent === 'Отправляем…'), 'состояние «Отправляем…», кнопка заблокирована');
  await page.waitForTimeout(900);
  ok(await page.$eval('#form-done', (e) => !e.hidden) && await page.$eval('#lead-form', (e) => e.hidden), 'панель успеха вместо формы');
  ok(await page.$('#form-done .done__link') !== null, 'кнопка Telegram-каталога есть в панели успеха');
  const payload = logs.find((l) => l.includes('[демо]'));
  ok(!!payload, 'демо-режим пишет payload в консоль');
  ok(logs.some((l) => l.includes('lead_success')), 'цель lead_success');
  ok(logs.some((l) => l.includes('form_start')), 'цель form_start');
  ok(logs.some((l) => l.includes('cta_click')), 'цель cta_click');

  await afterForm();
  await page.waitForTimeout(400);
  ok(!(await sticky()), 'липкая кнопка не возвращается после успеха');

  const before = await page.$$eval('a', (as) => as.filter((a) => a.textContent.includes('Telegram') && a.closest('#form-done') === null && /каталог|актуальн/i.test(a.textContent)).length);
  ok(before === 0, 'Telegram-каталог нигде вне панели успеха');

  await browser.close();
  console.log(failed ? `\nПровалено: ${failed}` : '\nВсе проверки пройдены');
  process.exit(failed ? 1 : 0);
})();
