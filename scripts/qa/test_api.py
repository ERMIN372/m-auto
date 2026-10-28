#!/usr/bin/env python3
"""Проверка api/send.php без реального Telegram.

    python3 scripts/build.py --env prod --allow-placeholders
    python3 scripts/qa/test_api.py

Поднимает заглушку Bot API на 127.0.0.1:8099 и `php -S` на 127.0.0.1:8080 (корень dist/),
пишет тестовый dist/api/config.php, гоняет сценарии и всё за собой убирает.
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"
API = "http://127.0.0.1:8080/api/send.php"
STUB_PORT = 8099

received: list[dict] = []
stub_mode = {"fail": False}
failed = 0


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        data = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}
        if stub_mode["fail"]:
            self.send_response(502)
            self.end_headers()
            return
        received.append({"path": self.path, **data})
        out = json.dumps({"ok": True, "result": {}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


def check(cond: bool, msg: str) -> None:
    global failed
    print(f"{'OK  ' if cond else 'FAIL'} {msg}")
    if not cond:
        failed += 1


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


opener = urllib.request.build_opener(NoRedirect)


def post(data: dict | str, json_mode: bool = True, headers: dict | None = None, method: str = "POST"):
    if json_mode:
        body = json.dumps(data).encode()
        h = {"Content-Type": "application/json", "Accept": "application/json"}
    else:
        body = urllib.parse.urlencode(data).encode()
        h = {"Content-Type": "application/x-www-form-urlencoded"}
    h.update(headers or {})
    req = urllib.request.Request(API, data=body if method == "POST" else None, headers=h, method=method)
    try:
        res = opener.open(req, timeout=15)
        return res.status, dict(res.headers), res.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def lead(**over) -> dict:
    base = {
        "name": "Алексей", "car": "Volkswagen Tiguan", "year_from": "2019", "year_to": "2022",
        "mileage_from": "", "mileage_to": "80 000", "contact": "+7 999 123-45-67",
        "contact_method": "messenger", "consent": "1",
        "utm_source": "yandex", "utm_medium": "cpc", "utm_campaign": "campaign_name",
        "utm_content": "", "utm_term": "авто из германии", "yclid": "777",
        "referrer": "https://yandex.ru/", "landing_url": "https://example.ru/?utm_source=yandex",
        "form_ts": str(int(time.time() * 1000)), "form_elapsed": "15000", "company_site": "",
    }
    base.update(over)
    return base


def main() -> int:
    if not (DIST / "api/send.php").exists():
        print("Сначала: python3 scripts/build.py --env prod --allow-placeholders")
        return 1
    storage = Path(tempfile.mkdtemp(prefix="mauto-storage-"))
    config = DIST / "api/config.php"
    config.write_text(f"""<?php
return [
  'bot_token' => 'TEST',
  'chat_ids' => ['-100123', '42'],
  'lead_email' => '',
  'storage_dir' => '{storage}',
  'site_host' => 'example.ru',
  'rate_limit' => ['max' => 8, 'window_sec' => 600],
  'min_fill_sec' => 3,
  'tg_api_base' => 'http://127.0.0.1:{STUB_PORT}',
];
""", encoding="utf-8")

    stub = ThreadingHTTPServer(("127.0.0.1", STUB_PORT), Stub)
    threading.Thread(target=stub.serve_forever, daemon=True).start()
    php = subprocess.Popen(["php", "-S", "127.0.0.1:8080", "-t", str(DIST)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.2)
    valid = 0
    try:
        code, _, _ = post({}, method="GET")
        check(code == 405, f"GET → 405 (получили {code})")

        code, _, body = post(lead())
        data = json.loads(body)
        valid += 1
        check(code == 200 and data.get("ok") is True and data.get("id") == 1001, f"валидная заявка → 200, id 1001 ({code} {body})")
        check(len(received) == 2, f"отправлено в оба чата ({len(received)})")
        msg = received[0]["text"] if received else ""
        check(received and received[0]["path"] == "/botTEST/sendMessage" and received[0]["parse_mode"] == "HTML", "sendMessage с parse_mode=HTML")
        for part in ["Заявка #1001</b> · M-AUTO", "Имя: Алексей", "Авто: Volkswagen Tiguan", "Год: 2019–2022",
                     "Пробег: до 80 000 км", "Связаться: написать в мессенджер", "Контакт: +7 999 123-45-67",
                     "wa.me/79991234567", "Источник: yandex / cpc / campaign_name", "Ключ: авто из германии",
                     "Страница: https://example.ru/?utm_source=yandex", "МСК"]:
            check(part in msg, f"в сообщении есть «{part}»")
        month = time.strftime("%Y-%m")
        csv_file = storage / f"leads-{month}.csv"
        raw = csv_file.read_bytes() if csv_file.exists() else b""
        check(raw.startswith(b"\xef\xbb\xbf"), "CSV в UTF-8 с BOM")
        text = raw.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        check(len(rows) == 2 and rows[0][:4] == ["id", "дата и время МСК", "имя", "авто"] and len(rows[0]) == 18
              and rows[1][0] == "1001" and rows[1][8] == "тел. +7 999 123-45-67" and rows[1][7] == "80000",
              "CSV: 18 колонок, разделитель «;», строка заявки")
        check("127.0.0.1" not in text, "IP в CSV не хранится")

        received.clear()
        code, _, body = post(lead(name="", car="X", year_from="2022", year_to="2019", contact="привет", consent=""))
        errs = json.loads(body).get("errors", {})
        check(code == 422 and {"name", "car", "year_to", "contact", "consent"} <= set(errs), f"кривые данные → 422 ({code}, {sorted(errs)})")
        check(errs.get("year_to") == "Год «до» не может быть раньше года «от»", "текст ошибки годов")
        code, _, body = post(lead(mileage_from="100000", mileage_to="50000"))
        check(code == 422 and "mileage_to" in json.loads(body).get("errors", {}), "пробег «до» меньше «от» → 422")
        code, _, body = post(lead(contact="@ivan_petrov", contact_method="call"))
        check(code == 422 and "телефон" in json.loads(body).get("errors", {}).get("contact", ""), "«позвонить» + ник → 422")
        check(not received, "при 422 в Telegram ничего не ушло")

        code, _, body = post(lead(company_site="http://spam.example"))
        check(code == 200 and json.loads(body) == {"ok": True} and not received, "ловушка → тихий «ок», ничего не отправлено")
        code, _, body = post(lead(form_elapsed="800"))
        check(code == 200 and json.loads(body) == {"ok": True} and not received, "отправка быстрее 3 с → тихий «ок»")

        code, _, _ = post(lead(), headers={"Origin": "https://evil.example"})
        check(code == 403 and not received, "чужой Origin → 403")
        code, _, _ = post(lead(), headers={"Origin": "https://www.example.ru"})
        valid += 1
        check(code == 200, "www.example.ru считается своим")

        received.clear()
        code, _, body = post(lead(name='<b>Вася</b> & "Ко"', contact="t.me/ivan_petrov"))
        valid += 1
        msg = received[0]["text"] if received else ""
        check(code == 200 and "&lt;b&gt;Вася&lt;/b&gt; &amp; &quot;Ко&quot;" in msg, "пользовательский ввод экранирован")
        check("Контакт: @ivan_petrov" in msg and 'href="https://t.me/ivan_petrov"' in msg and "wa.me" not in msg,
              "Telegram из ссылки t.me: только ссылка на Telegram")

        received.clear()
        code, _, body = post(lead(contact="8 (912) 000-11-22", contact_method="call", mileage_from="50000", mileage_to=""))
        valid += 1
        msg = received[0]["text"] if received else ""
        check("Контакт: +7 912 000-11-22" in msg and "Связаться: позвонить" in msg and "Пробег: от 50 000 км" in msg,
              "телефон 8… нормализован в +7, способ «позвонить», пробег «от»")
        code, _, _ = post(lead(contact="9120001122"))
        valid += 1
        check(code == 200, "10 цифр на 9 → принят как +7")

        received.clear()
        code, headers, _ = post(lead(), json_mode=False)
        valid += 1
        check(code == 303 and headers.get("Location") == "../spasibo/", f"обычный POST без JS → 303 на ../spasibo/ ({code})")
        code, headers, body = post(lead(name=""), json_mode=False)
        check(code == 422 and "text/html" in headers.get("Content-Type", "") and "Напишите, как к вам обращаться" in body,
              "обычный POST с ошибкой → HTML со списком ошибок")

        received.clear()
        stub_mode["fail"] = True
        code, _, body = post(lead(name="Без телеграма"))
        valid += 1
        stub_mode["fail"] = False
        log = (storage / "errors.log").read_text(encoding="utf-8") if (storage / "errors.log").exists() else ""
        rows = (storage / f"leads-{month}.csv").read_text(encoding="utf-8-sig")
        check(code == 200 and json.loads(body).get("ok") is True, "Telegram недоступен → пользователю всё равно успех")
        check("не ушла в Telegram" in log and "Без телеграма" in rows, "ошибка в errors.log, заявка в CSV")
        check("Без телеграма" not in log, "в errors.log нет персональных данных")

        statuses = []
        for _ in range(10):
            code, _, _ = post(lead())
            statuses.append(code)
            if code == 429:
                break
        check(429 in statuses and statuses.count(200) == 8 - valid, f"лимит частоты: 429 после {8} заявок ({statuses})")

        counter = (storage / "counter.txt").read_text().strip()
        check(counter == str(1000 + 8), f"счётчик заявок с flock: {counter}")
    finally:
        php.terminate()
        stub.shutdown()
        config.unlink(missing_ok=True)
        shutil.rmtree(storage, ignore_errors=True)

    print("\nВсе проверки пройдены" if not failed else f"\nПровалено: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
