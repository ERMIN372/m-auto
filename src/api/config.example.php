<?php
/**
 * Настройки обработчика заявок.
 * Скопируйте файл в config.php рядом с ним и заполните. config.php в git не попадает.
 */
return [
  'bot_token'     => '',            // токен от @BotFather
  'chat_ids'      => [''],          // один или несколько чатов, у групп id отрицательный
  'lead_email'    => '',            // необязательно: дубль заявок на почту
  'storage_dir'   => __DIR__ . '/storage', // лучше вне web-root, если хостинг позволяет
  'site_host'     => 'example.ru',  // для мягкой проверки Origin/Referer; кириллический домен — в punycode
  'rate_limit'    => ['max' => 5, 'window_sec' => 600],
  'min_fill_sec'  => 3,
  // 'tg_api_base' => 'https://api.telegram.org', // менять только для теста или прокси
];
