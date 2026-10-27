# Источники и лицензии

## Шрифт

**Onest** (variable), дизайнеры Dmitri Voloshin, Andrey Kudryavtsev.
Copyright 2021 The Onest Project Authors (https://github.com/simpals/onest).
Лицензия: SIL Open Font License 1.1, разрешает коммерческое использование и встраивание в сайты.

- Источник: https://github.com/google/fonts/tree/main/ofl/onest
- Исходный файл и текст лицензии: `scripts/fonts/Onest-wght.ttf`, `scripts/fonts/OFL.txt`
- На сайте: подмножество `src/assets/fonts/onest-var.woff2` (латиница, кириллица, ось wght 400–650), собрано `scripts/subset_font.py`

## Изображения

Сторонних фото в превью нет. Фотостоки (Unsplash, Pexels) были недоступны из среды разработки, поэтому стоят собственные заглушки:

- силуэты авто и клиента: `src/assets/img/placeholders/*.svg`, сгенерированы `scripts/make_placeholders.py`;
- фавиконки и OG-картинка: собственная монограмма и типографика, `scripts/optimize_images.py --icons`;
- иконки интерфейса (часы, документ, галочки): собственные inline SVG.

Фото заказчика (первый экран, кейсы, клиенты) добавляются по `CONTENT_TO_REPLACE.md`. Если будут использоваться фото со стоков, запишите сюда источник, автора и лицензию каждого снимка.

## Сторонние сервисы

- **Яндекс Метрика** (ООО «ЯНДЕКС»): подключается только в prod-сборке при заданном `metrika_id`.
- **Telegram Bot API**: отправка заявок из `api/send.php` на сервере, браузер посетителя к Telegram не обращается.
