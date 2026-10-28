#!/usr/bin/env bash
# Сквозная проверка prod-сборки с заглушкой Telegram. Запуск: bash scripts/qa/e2e_prod.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 scripts/build.py --env prod --allow-placeholders >/dev/null
STORAGE="$(mktemp -d)"
cat > dist/api/config.php <<PHP
<?php
return ['bot_token' => 'TEST', 'chat_ids' => ['1'], 'storage_dir' => '$STORAGE', 'site_host' => '',
        'tg_api_base' => 'http://127.0.0.1:8099'];
PHP
python3 - <<'PY' &
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(b'{"ok":true}')
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", 8099), H).serve_forever()
PY
STUB=$!
php -S 127.0.0.1:8080 -t dist >/dev/null 2>&1 &
PHP_PID=$!
trap 'kill $STUB $PHP_PID 2>/dev/null; rm -f dist/api/config.php; rm -rf "$STORAGE"' EXIT
sleep 1
node scripts/qa/e2e_prod.js http://127.0.0.1:8080/
echo "CSV:"; cat "$STORAGE"/leads-*.csv | tail -2
