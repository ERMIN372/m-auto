<?php
/**
 * M-AUTO: приём заявок с сайта.
 *
 * Порядок: валидация → запись в CSV на хостинге → Telegram → (опц.) почта → ответ.
 * Принимает JSON (fetch из main.js) и обычный POST формы (без JS → 303 на ../spasibo/).
 * Настройки: api/config.php (образец: config.example.php).
 */

declare(strict_types=1);

// подставляет scripts/build.py из site.config.json
const CONSENT_MODE = '{{consent_mode}}';
const CONTACT_PHONE = '{{phone_display}}';
const CONTACT_PHONE_E164 = '{{phone_e164}}';

const BRAND = 'M-AUTO';
const COUNTER_START = 1000;      // первая заявка получит № 1001
const MAX_BODY = 16384;
const TZ_NAME = 'Europe/Moscow';

const ALLOWED_FIELDS = [
    'name', 'car', 'year_from', 'year_to', 'mileage_from', 'mileage_to',
    'contact', 'contact_method', 'consent',
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'yclid',
    'referrer', 'landing_url', 'form_ts', 'form_elapsed', 'company_site',
];

// на редких хостингах без mbstring
if (!function_exists('mb_strlen')) {
    function mb_strlen(string $s): int
    {
        return (int) preg_match_all('/./us', $s);
    }
    function mb_substr(string $s, int $start, ?int $length = null): string
    {
        preg_match_all('/./us', $s, $m);
        return implode('', array_slice($m[0], $start, $length));
    }
    function mb_check_encoding(string $s, string $encoding = 'UTF-8'): bool
    {
        return preg_match('//u', $s) === 1;
    }
}

header('X-Content-Type-Options: nosniff');
header('Cache-Control: no-store');
header('Referrer-Policy: same-origin');

$isJson = str_contains(strtolower((string) ($_SERVER['CONTENT_TYPE'] ?? '')), 'application/json');

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    header('Allow: POST');
    respond(405, ['ok' => false], $isJson);
}

$config = load_config();
if ($config === null) {
    error_log('M-AUTO: нет api/config.php');
    respond(500, ['ok' => false], $isJson);
}

if (!origin_ok((string) $config['site_host'])) {
    log_error($config, 'запрос с чужого адреса отклонён');
    respond(403, ['ok' => false], $isJson);
}

$input = read_input($isJson);
if ($input === null) {
    respond(400, ['ok' => false], $isJson);
}

// антиспам: ловушка или слишком быстрая отправка → тихий «ок», ничего не шлём
if (is_spam($input, $config)) {
    respond(200, ['ok' => true], $isJson);
}

[$lead, $errors] = validate_lead($input);
if ($errors) {
    respond(422, ['ok' => false, 'errors' => $errors], $isJson);
}

$storage = prepare_storage($config);
if ($storage !== null && !rate_limit_ok($storage, $config)) {
    respond(429, ['ok' => false], $isJson);
}

$now = new DateTimeImmutable('now', new DateTimeZone(TZ_NAME));
$lead['id'] = $storage !== null ? next_id($storage) : null;
$lead['created'] = $now->format('d.m.Y H:i');
$lead['month'] = $now->format('Y-m');

$saved = $storage !== null && save_csv($storage, $lead);
if (!$saved) {
    log_error($config, 'заявка #' . ($lead['id'] ?? '—') . ' не записана в CSV');
}

$message = telegram_message($lead);
$sent = send_telegram($config, $message);
if (!$sent) {
    log_error($config, 'заявка #' . ($lead['id'] ?? '—') . ' не ушла в Telegram');
}

if ((string) $config['lead_email'] !== '') {
    if (!send_email($config, $lead, $message)) {
        log_error($config, 'заявка #' . ($lead['id'] ?? '—') . ' не ушла на почту');
    }
}

if (!$saved && !$sent) {
    respond(500, ['ok' => false], $isJson);
}

respond(200, ['ok' => true, 'id' => $lead['id']], $isJson);


// ====================================================================== конфиг и вход

function load_config(): ?array
{
    $file = __DIR__ . '/config.php';
    if (!is_file($file)) {
        return null;
    }
    $cfg = require $file;
    if (!is_array($cfg)) {
        return null;
    }
    $defaults = [
        'bot_token' => '',
        'chat_ids' => [],
        'lead_email' => '',
        'storage_dir' => __DIR__ . '/storage',
        'site_host' => '',
        'rate_limit' => ['max' => 5, 'window_sec' => 600],
        'min_fill_sec' => 3,
        'tg_api_base' => 'https://api.telegram.org',
    ];
    $cfg = array_replace($defaults, $cfg);
    $cfg['chat_ids'] = array_values(array_filter(array_map('strval', (array) $cfg['chat_ids']), 'strlen'));
    $cfg['rate_limit'] = array_replace($defaults['rate_limit'], (array) $cfg['rate_limit']);
    return $cfg;
}

function origin_ok(string $siteHost): bool
{
    if ($siteHost === '') {
        return true;
    }
    $source = (string) ($_SERVER['HTTP_ORIGIN'] ?? $_SERVER['HTTP_REFERER'] ?? '');
    if ($source === '' || $source === 'null') {
        return true; // браузер мог не прислать заголовок: не теряем заявку
    }
    $host = parse_url($source, PHP_URL_HOST);
    if (!is_string($host) || $host === '') {
        return true;
    }
    $norm = static fn (string $h): string => preg_replace('/^www\./', '', strtolower($h)) ?? $h;
    return $norm($host) === $norm($siteHost);
}

function read_input(bool $isJson): ?array
{
    if ($isJson) {
        $raw = file_get_contents('php://input', false, null, 0, MAX_BODY + 1);
        if ($raw === false || strlen($raw) > MAX_BODY) {
            return null;
        }
        $data = json_decode($raw, true);
        if (!is_array($data)) {
            return null;
        }
    } else {
        $data = $_POST;
    }
    $clean = [];
    foreach (ALLOWED_FIELDS as $field) {
        $value = $data[$field] ?? '';
        $value = is_scalar($value) ? (string) $value : '';
        if (!mb_check_encoding($value, 'UTF-8')) {
            $value = '';
        }
        // управляющие символы убираем, пробелы схлопываем
        $value = preg_replace('/[\x00-\x1F\x7F]+/u', ' ', $value) ?? '';
        $value = trim(preg_replace('/\s+/u', ' ', $value) ?? '');
        $clean[$field] = mb_substr($value, 0, 500);
    }
    return $clean;
}

function is_spam(array $in, array $cfg): bool
{
    if ($in['company_site'] !== '') {
        return true;
    }
    // время заполнения считает браузер: так не мешают сбитые часы у посетителя
    if ($in['form_elapsed'] !== '' && ctype_digit($in['form_elapsed'])) {
        return (int) $in['form_elapsed'] < (int) $cfg['min_fill_sec'] * 1000;
    }
    return false;
}


// ====================================================================== проверка полей (те же правила, что в main.js)

function validate_lead(array $in): array
{
    $errors = [];
    $lead = [];

    $name = $in['name'];
    $len = mb_strlen($name);
    if ($len === 0) {
        $errors['name'] = 'Напишите, как к вам обращаться';
    } elseif ($len < 2) {
        $errors['name'] = 'Имя слишком короткое: нужно хотя бы 2 символа';
    } elseif ($len > 60) {
        $errors['name'] = 'Имя слишком длинное: не больше 60 символов';
    }
    $lead['name'] = $name;

    $car = $in['car'];
    $len = mb_strlen($car);
    if ($len === 0) {
        $errors['car'] = 'Напишите марку и модель, например Volkswagen Tiguan';
    } elseif ($len < 2) {
        $errors['car'] = 'Слишком коротко: напишите марку и модель';
    } elseif ($len > 80) {
        $errors['car'] = 'Слишком длинно: не больше 80 символов';
    }
    $lead['car'] = $car;

    // диапазон с запасом: страница могла быть собрана в прошлом году
    $maxYear = (int) date('Y') + 1;
    $yearOk = static fn (string $v): bool => ctype_digit($v) && (int) $v >= 1950 && (int) $v <= $maxYear;
    $from = $in['year_from'];
    $to = $in['year_to'];
    if (!$yearOk($from)) {
        $errors['year_from'] = 'Выберите год выпуска «от»';
    }
    if (!$yearOk($to)) {
        $errors['year_to'] = 'Выберите год выпуска «до»';
    } elseif ($yearOk($from) && (int) $to < (int) $from) {
        $errors['year_to'] = 'Год «до» не может быть раньше года «от»';
    }
    $lead['year_from'] = $from;
    $lead['year_to'] = $to;

    $milFrom = preg_replace('/\D/', '', $in['mileage_from']) ?? '';
    $milTo = preg_replace('/\D/', '', $in['mileage_to']) ?? '';
    $milFrom = $milFrom === '' ? '' : (string) (int) $milFrom;
    $milTo = $milTo === '' ? '' : (string) (int) $milTo;
    if (strlen($milFrom) > 7) {
        $errors['mileage_from'] = 'Слишком большое число';
    }
    if (strlen($milTo) > 7) {
        $errors['mileage_to'] = 'Слишком большое число';
    } elseif ($milFrom !== '' && $milTo !== '' && (int) $milTo < (int) $milFrom) {
        $errors['mileage_to'] = 'Пробег «до» не может быть меньше пробега «от»';
    }
    $lead['mileage_from'] = $milFrom;
    $lead['mileage_to'] = $milTo;

    $method = $in['contact_method'] === 'call' ? 'call' : 'messenger';
    $lead['contact_method'] = $method;

    $contactRaw = $in['contact'];
    $parsed = parse_contact($contactRaw);
    if ($contactRaw === '') {
        $errors['contact'] = $method === 'call' ? 'Укажите телефон для звонка' : 'Укажите телефон или ник в Telegram';
    } elseif ($method === 'call' && ($parsed === null || $parsed['type'] !== 'phone')) {
        $errors['contact'] = 'Для звонка нужен номер телефона, например +7 999 123-45-67';
    } elseif ($parsed === null) {
        $errors['contact'] = 'Не похоже на телефон или ник Telegram. Пример: +7 999 123-45-67 или @username';
    }
    $lead['contact'] = $parsed;

    $consentMode = str_starts_with(CONSENT_MODE, '{{') ? 'checkbox' : CONSENT_MODE;
    if ($consentMode === 'checkbox' && $in['consent'] !== '1') {
        $errors['consent'] = 'Поставьте галочку: без согласия мы не можем принять заявку';
    }

    foreach (['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'yclid'] as $k) {
        $lead[$k] = mb_substr($in[$k], 0, 200);
    }
    $lead['landing_url'] = safe_url($in['landing_url']);
    $lead['referrer'] = safe_url($in['referrer']);

    return [$lead, $errors];
}

function parse_phone(string $value): ?string
{
    $v = trim($value);
    if ($v === '' || !preg_match('/^[+\d\s().-]+$/', $v)) {
        return null;
    }
    $d = preg_replace('/\D/', '', $v) ?? '';
    if ($v[0] === '+') {
        if (strlen($d) === 11 && $d[0] === '7') {
            return '+' . $d;
        }
        return strlen($d) >= 10 && strlen($d) <= 15 ? '+' . $d : null;
    }
    if (strlen($d) === 11 && ($d[0] === '7' || $d[0] === '8')) {
        return '+7' . substr($d, 1);
    }
    if (strlen($d) === 10 && $d[0] === '9') {
        return '+7' . $d;
    }
    return null;
}

/** @return array{type: string, value: string}|null */
function parse_contact(string $value): ?array
{
    $v = trim($value);
    if (preg_match('~^(?:https?://)?(?:wa\.me/|api\.whatsapp\.com/send/?\?phone=)\+?(\d{10,15})/?$~i', $v, $m)) {
        $phone = parse_phone($m[1]);
        return $phone ? ['type' => 'phone', 'value' => $phone] : null;
    }
    $phone = parse_phone($v);
    if ($phone !== null) {
        return ['type' => 'phone', 'value' => $phone];
    }
    if (preg_match('~^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/@?([a-z][a-z0-9_]{3,31})/?$~i', $v, $m)
        || preg_match('~^@?([a-z][a-z0-9_]{3,31})$~i', $v, $m)) {
        return ['type' => 'telegram', 'value' => $m[1]];
    }
    return null;
}

function safe_url(string $url): string
{
    $url = mb_substr($url, 0, 500);
    return preg_match('~^https?://~i', $url) ? $url : '';
}

function format_phone(string $e164): string
{
    if (preg_match('/^\+7(\d{3})(\d{3})(\d{2})(\d{2})$/', $e164, $m)) {
        return "+7 {$m[1]} {$m[2]}-{$m[3]}-{$m[4]}";
    }
    return $e164;
}

function format_km(string $n): string
{
    return number_format((int) $n, 0, '', ' ') . ' км';
}


// ====================================================================== хранение

function prepare_storage(array $cfg): ?string
{
    $dir = rtrim((string) $cfg['storage_dir'], '/');
    if (!is_dir($dir) && !@mkdir($dir, 0750, true)) {
        error_log('M-AUTO: не удалось создать storage: ' . $dir);
        return null;
    }
    if (!is_writable($dir)) {
        error_log('M-AUTO: storage недоступен для записи: ' . $dir);
        return null;
    }
    // на случай, если папку создали заново внутри сайта
    $ht = $dir . '/.htaccess';
    if (!is_file($ht)) {
        @file_put_contents($ht, "Require all denied\n");
    }
    return $dir;
}

function locked_update(string $file, callable $fn): mixed
{
    $fh = @fopen($file, 'c+');
    if ($fh === false) {
        return null;
    }
    try {
        if (!flock($fh, LOCK_EX)) {
            return null;
        }
        $content = stream_get_contents($fh);
        $result = $fn($content === false ? '' : $content);
        [$newContent, $return] = $result;
        if ($newContent !== null) {
            ftruncate($fh, 0);
            rewind($fh);
            fwrite($fh, $newContent);
            fflush($fh);
        }
        flock($fh, LOCK_UN);
        return $return;
    } finally {
        fclose($fh);
    }
}

function next_id(string $dir): ?int
{
    return locked_update($dir . '/counter.txt', static function (string $c): array {
        $n = max((int) trim($c), COUNTER_START) + 1;
        return [(string) $n, $n];
    });
}

function rate_limit_ok(string $dir, array $cfg): bool
{
    $max = max(1, (int) $cfg['rate_limit']['max']);
    $window = max(1, (int) $cfg['rate_limit']['window_sec']);
    $rlDir = $dir . '/ratelimit';
    if (!is_dir($rlDir) && !@mkdir($rlDir, 0750, true)) {
        return true; // без лимита лучше, чем без заявки
    }
    // сам IP не храним: только хэш с солью этого сайта
    $ip = (string) ($_SERVER['REMOTE_ADDR'] ?? '');
    $key = hash('sha256', salt($dir) . '|' . $ip);
    $now = time();
    $ok = locked_update($rlDir . '/' . substr($key, 0, 32), static function (string $c) use ($now, $window, $max): array {
        $times = array_filter(array_map('intval', explode("\n", trim($c))), static fn (int $t): bool => $t > $now - $window);
        if (count($times) >= $max) {
            return [implode("\n", $times), false];
        }
        $times[] = $now;
        return [implode("\n", $times), true];
    });
    if (random_int(1, 50) === 1) {
        cleanup_rate_limit($rlDir, $window);
    }
    return $ok !== false;
}

function cleanup_rate_limit(string $rlDir, int $window): void
{
    foreach ((array) glob($rlDir . '/*') as $file) {
        if (is_string($file) && is_file($file) && filemtime($file) < time() - $window * 2) {
            @unlink($file);
        }
    }
}

function salt(string $dir): string
{
    $file = $dir . '/.salt';
    $salt = is_file($file) ? trim((string) file_get_contents($file)) : '';
    if ($salt === '') {
        $salt = bin2hex(random_bytes(16));
        @file_put_contents($file, $salt, LOCK_EX);
    }
    return $salt;
}

/** Excel не должен принять значение за формулу */
function csv_cell(string $v): string
{
    return preg_match('/^[=+\-@\t\r]/', $v) ? "'" . $v : $v;
}

function contact_cell(?array $c): string
{
    if ($c === null) {
        return '';
    }
    return $c['type'] === 'phone' ? 'тел. ' . format_phone($c['value']) : 'tg @' . $c['value'];
}

function save_csv(string $dir, array $lead): bool
{
    $file = $dir . '/leads-' . $lead['month'] . '.csv';
    $header = ['id', 'дата и время МСК', 'имя', 'авто', 'год от', 'год до', 'пробег от', 'пробег до',
        'контакт', 'способ связи', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
        'yclid', 'страница', 'referrer'];
    $row = [
        (string) ($lead['id'] ?? ''), $lead['created'], $lead['name'], $lead['car'],
        $lead['year_from'], $lead['year_to'], $lead['mileage_from'], $lead['mileage_to'],
        contact_cell($lead['contact']),
        $lead['contact_method'] === 'call' ? 'позвонить' : 'написать в мессенджер',
        $lead['utm_source'], $lead['utm_medium'], $lead['utm_campaign'], $lead['utm_content'], $lead['utm_term'],
        $lead['yclid'], $lead['landing_url'], $lead['referrer'],
    ];
    $fh = @fopen($file, 'a');
    if ($fh === false) {
        return false;
    }
    try {
        if (!flock($fh, LOCK_EX)) {
            return false;
        }
        clearstatcache(true, $file);
        if (filesize($file) === 0) {
            fwrite($fh, "\xEF\xBB\xBF"); // BOM: русский Excel откроет в UTF-8
            fputcsv($fh, $header, ';', '"', '');
        }
        $ok = fputcsv($fh, array_map('csv_cell', $row), ';', '"', '') !== false;
        fflush($fh);
        flock($fh, LOCK_UN);
        return $ok;
    } finally {
        fclose($fh);
    }
}

function log_error(array $cfg, string $message): void
{
    // в лог только номер и тип ошибки, без персональных данных
    $dir = rtrim((string) $cfg['storage_dir'], '/');
    $line = (new DateTimeImmutable('now', new DateTimeZone(TZ_NAME)))->format('Y-m-d H:i:s') . ' МСК  ' . $message . "\n";
    if (!is_dir($dir) || @file_put_contents($dir . '/errors.log', $line, FILE_APPEND | LOCK_EX) === false) {
        error_log('M-AUTO: ' . $message);
    }
}


// ====================================================================== Telegram и почта

function h(string $s): string
{
    return htmlspecialchars($s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function telegram_message(array $lead): string
{
    $id = $lead['id'] !== null ? '#' . $lead['id'] : 'без номера';
    $years = $lead['year_from'] === $lead['year_to'] ? $lead['year_from'] : $lead['year_from'] . '–' . $lead['year_to'];

    $from = $lead['mileage_from'];
    $to = $lead['mileage_to'];
    if ($from !== '' && $to !== '') {
        $mileage = $from === $to ? format_km($from) : number_format((int) $from, 0, '', ' ') . '–' . format_km($to);
    } elseif ($to !== '') {
        $mileage = 'до ' . format_km($to);
    } elseif ($from !== '') {
        $mileage = 'от ' . format_km($from);
    } else {
        $mileage = 'не указан';
    }

    $c = $lead['contact'];
    if ($c['type'] === 'phone') {
        $digits = ltrim($c['value'], '+');
        $contact = format_phone($c['value']);
        $links = [
            'WhatsApp: <a href="https://wa.me/' . $digits . '">wa.me/' . $digits . '</a>',
            'Telegram: <a href="https://t.me/+' . $digits . '">t.me/+' . $digits . '</a>',
            'Позвонить: ' . h($c['value']),
        ];
    } else {
        $contact = '@' . $c['value'];
        $links = ['Telegram: <a href="https://t.me/' . $c['value'] . '">t.me/' . $c['value'] . '</a>'];
    }

    $lines = [
        '🚗 <b>Заявка ' . h($id) . '</b> · ' . BRAND,
        'Имя: ' . h($lead['name']),
        'Авто: ' . h($lead['car']),
        'Год: ' . h($years),
        'Пробег: ' . h($mileage),
        'Связаться: ' . ($lead['contact_method'] === 'call' ? 'позвонить' : 'написать в мессенджер'),
        'Контакт: ' . h($contact),
        implode(' · ', $links),
        '',
    ];
    $source = array_filter([$lead['utm_source'], $lead['utm_medium'], $lead['utm_campaign']], 'strlen');
    if ($source) {
        $lines[] = 'Источник: ' . h(implode(' / ', $source));
    }
    if ($lead['utm_term'] !== '') {
        $lines[] = 'Ключ: ' . h($lead['utm_term']);
    }
    if ($lead['landing_url'] !== '') {
        $lines[] = 'Страница: ' . h($lead['landing_url']);
    }
    $lines[] = h($lead['created']) . ' МСК';
    return implode("\n", $lines);
}

function send_telegram(array $cfg, string $text): bool
{
    $token = (string) $cfg['bot_token'];
    if ($token === '' || !$cfg['chat_ids']) {
        return false;
    }
    $url = rtrim((string) $cfg['tg_api_base'], '/') . '/bot' . $token . '/sendMessage';
    $okAny = false;
    foreach ($cfg['chat_ids'] as $chatId) {
        $body = http_build_query([
            'chat_id' => $chatId,
            'text' => $text,
            'parse_mode' => 'HTML',
            'disable_web_page_preview' => 'true',
        ]);
        $response = http_post($url, $body);
        $data = $response !== null ? json_decode($response, true) : null;
        if (is_array($data) && ($data['ok'] ?? false) === true) {
            $okAny = true;
        } else {
            $desc = is_array($data) ? (string) ($data['description'] ?? 'неизвестная ошибка') : 'нет ответа';
            log_error($cfg, 'Telegram, чат ' . $chatId . ': ' . mb_substr($desc, 0, 200));
        }
    }
    return $okAny;
}

function http_post(string $url, string $body): ?string
{
    if (function_exists('curl_init')) {
        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => $body,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_CONNECTTIMEOUT => 5,
            CURLOPT_TIMEOUT => 5,
            CURLOPT_HTTPHEADER => ['Content-Type: application/x-www-form-urlencoded'],
        ]);
        $result = curl_exec($ch);
        curl_close($ch);
        return is_string($result) ? $result : null;
    }
    $ctx = stream_context_create(['http' => [
        'method' => 'POST',
        'header' => "Content-Type: application/x-www-form-urlencoded\r\n",
        'content' => $body,
        'timeout' => 5,
        'ignore_errors' => true,
    ]]);
    $result = @file_get_contents($url, false, $ctx);
    return is_string($result) ? $result : null;
}

function send_email(array $cfg, array $lead, string $telegramText): bool
{
    $to = (string) $cfg['lead_email'];
    if (!filter_var($to, FILTER_VALIDATE_EMAIL)) {
        return false;
    }
    $host = (string) ($cfg['site_host'] ?: ($_SERVER['HTTP_HOST'] ?? 'localhost'));
    $host = preg_replace('/[^a-z0-9.\-]/i', '', $host) ?: 'localhost';
    $subject = 'Заявка ' . ($lead['id'] !== null ? '#' . $lead['id'] : '') . ' с сайта ' . BRAND;
    $text = html_entity_decode(strip_tags(str_replace('🚗 ', '', $telegramText)), ENT_QUOTES | ENT_HTML5, 'UTF-8');
    $headers = implode("\r\n", [
        'From: ' . BRAND . ' <no-reply@' . $host . '>',
        'MIME-Version: 1.0',
        'Content-Type: text/plain; charset=UTF-8',
        'Content-Transfer-Encoding: 8bit',
    ]);
    return @mail($to, '=?UTF-8?B?' . base64_encode($subject) . '?=', $text, $headers);
}


// ====================================================================== ответ

function respond(int $code, array $body, bool $isJson): void
{
    http_response_code($code);
    if ($isJson) {
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode($body, JSON_UNESCAPED_UNICODE);
        exit;
    }
    // обычная отправка формы без JavaScript
    if ($code === 200) {
        header('Location: ../spasibo/', true, 303);
        exit;
    }
    header('Content-Type: text/html; charset=utf-8');
    $phone = str_starts_with(CONTACT_PHONE, '{{') ? '' : CONTACT_PHONE;
    $phoneLink = $phone !== '' ? '<p>Или позвоните: <a href="tel:' . h(CONTACT_PHONE_E164) . '">' . h($phone) . '</a></p>' : '';
    if ($code === 422) {
        $title = 'Проверьте заявку';
        $items = '';
        foreach ($body['errors'] ?? [] as $msg) {
            $items .= '<li>' . h((string) $msg) . '</li>';
        }
        $content = '<ul>' . $items . '</ul><p><a href="../#form" onclick="history.back();return false">Вернуться к форме</a></p>';
    } elseif ($code === 429) {
        $title = 'Слишком много заявок подряд';
        $content = '<p>Подождите несколько минут и попробуйте ещё раз.</p>' . $phoneLink;
    } else {
        $title = 'Не получилось отправить заявку';
        $content = '<p>Попробуйте ещё раз чуть позже.</p>' . $phoneLink;
    }
    echo '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        . '<meta name="robots" content="noindex"><title>' . h($title) . ' | ' . BRAND . '</title>'
        . '<style>body{font:18px/1.5 system-ui,sans-serif;color:#141617;max-width:40rem;margin:0 auto;padding:2rem 1.25rem}a{color:inherit}</style>'
        . '</head><body><h1>' . h($title) . '</h1>' . $content . '</body></html>';
    exit;
}
