<?php
/**
 * Досылка заявок в Telegram, которые не ушли из-за обрыва связи.
 * Запускается из start.sh раз в минуту, только из командной строки, лежит вне сайта.
 * Очередь: <storage_dir>/tg-pending.jsonl (её пишет send.php).
 */
if (PHP_SAPI !== 'cli') {
    exit(1);
}
$cfg = require (getenv('M_AUTO_CONFIG') ?: '/var/www/html/api/config.php');
$token = (string) ($cfg['bot_token'] ?? '');
$file = rtrim((string) ($cfg['storage_dir'] ?? ''), '/') . '/tg-pending.jsonl';
if ($token === '' || !is_file($file)) {
    exit(0);
}
$fh = fopen($file, 'c+');
if ($fh === false || !flock($fh, LOCK_EX)) {
    exit(0);
}
$lines = array_filter(explode("\n", (string) stream_get_contents($fh)));
$left = [];
$sent = 0;
foreach ($lines as $line) {
    $item = json_decode($line, true);
    if (!is_array($item) || empty($item['chat_id']) || !isset($item['text'])) {
        continue;
    }
    // старше суток не досылаем: менеджер увидит заявку в CSV
    if (time() - (int) ($item['queued'] ?? 0) > 86400) {
        error_log('M-AUTO: досылка: сообщение старше суток удалено из очереди');
        continue;
    }
    $mins = max(1, (int) round((time() - (int) $item['queued']) / 60));
    $ch = curl_init(rtrim((string) ($cfg['tg_api_base'] ?? 'https://api.telegram.org'), '/') . '/bot' . $token . '/sendMessage');
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => http_build_query([
            'chat_id' => $item['chat_id'],
            'text' => '⏳ Доставлено с задержкой ' . $mins . ' мин' . "\n" . $item['text'],
            'parse_mode' => 'HTML',
            'disable_web_page_preview' => 'true',
        ]),
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => 5,
        CURLOPT_TIMEOUT => 10,
    ]);
    $res = curl_exec($ch);
    $err = curl_error($ch);
    curl_close($ch);
    $data = is_string($res) ? json_decode($res, true) : null;
    if (is_array($data) && ($data['ok'] ?? false) === true) {
        $sent++;
    } elseif (is_array($data)) {
        // Telegram ответил отказом (чат, токен): повтор не поможет
        error_log('M-AUTO: досылка: отказ Telegram: ' . substr((string) ($data['description'] ?? ''), 0, 200));
    } else {
        $left[] = $line;
        error_log('M-AUTO: досылка: нет ответа' . ($err !== '' ? ' (' . $err . ')' : '') . ', в очереди ' . count($left));
    }
}
ftruncate($fh, 0);
rewind($fh);
fwrite($fh, $left ? implode("\n", $left) . "\n" : '');
flock($fh, LOCK_UN);
fclose($fh);
if ($sent > 0) {
    error_log('M-AUTO: досылка: отправлено ' . $sent);
}
