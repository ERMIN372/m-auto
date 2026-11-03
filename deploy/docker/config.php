<?php
// Секреты не в файле: берутся из переменных окружения проекта на хостинге.
// BOT_TOKEN, TG_CHAT_IDS (через запятую), необязательно WEBHOOK_URL, WEBHOOK_ONLY=1, LEAD_EMAIL.
$env = static function (string $k): string {
    $v = getenv($k);
    if ($v === false || $v === '') {
        $v = $_SERVER[$k] ?? $_ENV[$k] ?? '';
    }
    return trim((string) $v);
};
return [
  'bot_token'   => $env('BOT_TOKEN'),
  'chat_ids'    => array_map('trim', explode(',', $env('TG_CHAT_IDS'))),
  'lead_email'  => $env('LEAD_EMAIL'),
  'storage_dir' => '/var/lib/m-auto/storage',
  'site_host'   => $env('SITE_HOST') !== '' ? $env('SITE_HOST') : 'm-auto-import.ru',
  'rate_limit'  => ['max' => 5, 'window_sec' => 600],
  'min_fill_sec'=> 3,
  'webhook_url' => $env('WEBHOOK_URL'),
  'webhook_replaces_telegram' => $env('WEBHOOK_ONLY') === '1',
];
