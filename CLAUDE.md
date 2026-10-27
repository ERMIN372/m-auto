# M-AUTO: лендинг подбора авто из Европы

Одностраничный лендинг, одна цель: заявка на подбор. ТЗ и технические требования: `M-AUTO_TASK.md` (не удалять). Приоритет: ТЗ заказчика (Приложение A) > `M-AUTO_TASK.md` > привычные решения.

## Стек
- HTML + CSS + vanilla JS, без фреймворков и npm-зависимостей в рантайме.
- Сборка: `scripts/build.py` (Python 3, только stdlib). Картинки: `scripts/optimize_images.py` (Pillow).
- Заявки: `src/api/send.php` (PHP 8) → CSV в storage → Telegram-бот → (опц.) почта.
- Шрифт: Onest variable, `src/assets/fonts/onest-var.woff2` (подмножество, wght 400–650). Исходник и OFL: `scripts/fonts/`.

## Команды
```bash
python3 scripts/build.py --env preview          # → docs/ (GitHub Pages, noindex, демо-форма)
python3 scripts/build.py --env prod             # → dist/ (падает, если есть заглушки)
python3 scripts/build.py --env prod --allow-placeholders   # тестовая prod-сборка
python3 scripts/build.py --env prod --config other.json    # сборка с другим конфигом (тесты)
python3 scripts/optimize_images.py              # raw/ → webp/jpg + manifest.json
python3 scripts/optimize_images.py --icons      # favicon.ico, apple-touch-icon.png, og-image.jpg
python3 scripts/make_placeholders.py            # SVG-заглушки фото
python3 -m http.server 8000 -d docs             # смотреть превью

# QA (Playwright с Chromium, PHP 8)
node scripts/qa/screens.js http://localhost:8000/ qa   # скриншоты 360/390/768/1440, внешние запросы
node scripts/qa/form.js http://localhost:8000/         # форма, все CTA, липкая кнопка, цели
python3 scripts/qa/test_api.py                         # send.php с заглушкой Telegram (после prod-сборки)
bash scripts/qa/e2e_prod.sh                            # prod-форма → send.php, с JS и без
```

## Структура
- `site.config.json`: все меняющиеся данные (`shared` + `preview`/`prod`).
- `src/`: исходники. `src/_partials/` вставляются через `<!-- include:name -->` и не копируются.
- `src/assets/img/raw/`: исходники фото (в .gitignore), `manifest.json` пишет optimize_images.py.
- `docs/`: сгенерированное превью, коммитится. `dist/`, `qa/`, `img/raw/`, `api/config.php`: в .gitignore.
- `CONTENT_TO_REPLACE.md`: все заглушки. `CREDITS.md`: лицензии.

## Шаблонизатор build.py
- `{{key}}`: значение из конфига; неизвестный ключ = ошибка сборки. `{{key|json}}`: экранирование для JSON-LD.
- `<!-- if:key -->…<!-- endif:key -->`: блок вырезается, если ключ пустой/false.
- `<!-- env:prod -->…<!-- endenv:prod -->`: блок только для env.
- `<!-- img:name alt="…" sizes="…" ph="car-hatch" [eager] [class="…"] -->`: `<picture>` если есть в `assets/img/manifest.json`, иначе SVG-заглушка с `data-placeholder`.
- `{{root}}`: относительный префикс до корня (`""` или `"../"`).
- Типограф (неразрывные пробелы) работает при сборке по текстовым узлам HTML: в исходниках пишем обычные пробелы.
- HTML-комментарии вырезаются из выходных файлов. Пометка заглушки: атрибут `data-placeholder` (prod-сборка на нём падает).

## Правила
- Тексты ТЗ дословно, кавычки ТЗ на сайт не переносить. Факты, цифры, имена, отзывы не выдумывать: только заглушки + запись в `CONTENT_TO_REPLACE.md`.
- Все пути относительные, без ведущего `/` (превью в подпапке GitHub Pages).
- Ни одного внешнего запроса из браузера. Исключение: Яндекс Метрика в prod при заданном `metrika_id`.
- Контент целиком в HTML, JS только улучшает.
- Основной CTA везде один: «Получить варианты». Не «Оставить заявку». Telegram-каталог только после успешной заявки.
- Акцентный цвет `--c-accent` только для CTA-кнопок. Выбранные состояния и фокус: графит/ink.
- Тени не используем. Скругления по ролям: 4 / 10 / 14 / 0.
- Не делать: FAQ, «О компании», каталог, калькулятор, длинные SEO-тексты, схемы из 7–10 этапов, таймеры, поп-апы, чат-виджеты, слайдеры, градиенты, стекло, fade-up, параллакс, эмодзи вместо иконок, капс-«глазки», подсветку слова в заголовке, мета-строки через «·», «→» в кнопках.
- Движение только как отклик на действие + `prefers-reduced-motion`.
- Поля формы ≥ 16px, зоны нажатия ≥ 48px.
- CSS: плоская специфичность (один класс), токены в `:root`.
