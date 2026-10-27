#!/usr/bin/env python3
"""Сборка лендинга M-AUTO.

    python3 scripts/build.py --env preview   → docs/  (GitHub Pages, noindex, демо-форма)
    python3 scripts/build.py --env prod      → dist/  (хостинг с PHP)
    python3 scripts/build.py --env prod --allow-placeholders   → тестовая prod-сборка

Только стандартная библиотека Python 3.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
CONFIG = ROOT / "site.config.json"
OUT_DIRS = {"preview": ROOT / "docs", "prod": ROOT / "dist"}

# файлы, которые проходят через шаблонизатор (css/js/svg копируются как есть)
TEMPLATE_SUFFIXES = {".html", ".txt", ".xml", ".php"}
TEMPLATE_NAMES = {".htaccess"}
SCAN_SUFFIXES = {".html", ".txt", ".xml"}

# в prod без этих ключей сайт не собирается
REQUIRED_PROD = [
    "site_url", "phone_e164", "phone_display", "email",
    "legal_name", "inn", "ogrn", "legal_address", "policy_date",
]
# эти могут быть пустыми: элементы с ними вырезаются, сборка предупреждает
OPTIONAL_PROD = [
    "whatsapp_url", "telegram_contact_url", "telegram_catalog_url",
    "metrika_id", "yandex_verification",
]
URL_KEYS = ["whatsapp_url", "telegram_contact_url", "telegram_catalog_url"]

# пометки заглушек: в prod их быть не должно
PLACEHOLDER_MARKERS = [
    "{{", "0000000000", "XX дней", "X XXX XXX", "20XX",
    "data-placeholder", "__.__", "example.ru",
]

NBSP = " "
YEARS_BACK = 20


class BuildError(Exception):
    pass


# ---------------------------------------------------------------- конфиг

def load_config(env: str, path: Path = CONFIG) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cfg = dict(raw.get("shared", {}))
    cfg.update(raw.get(env, {}))
    return cfg


def stringify(value) -> str:
    if value is True:
        return "true"
    if value is False or value is None:
        return ""
    return str(value)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def make_context(cfg: dict, env: str) -> dict:
    ctx = {k: stringify(v) for k, v in cfg.items()}
    ctx["site_url"] = ctx.get("site_url", "").rstrip("/")
    now = dt.datetime.now()
    year = now.year
    ctx["env"] = env
    ctx["is_preview"] = "1" if env == "preview" else ""
    ctx["is_prod"] = "1" if env == "prod" else ""
    ctx["year"] = str(year)
    ctx["build_date"] = now.date().isoformat()
    ctx["year_options"] = "".join(
        f'<option value="{y}">{y}</option>' for y in range(year, year - YEARS_BACK - 1, -1)
    )
    ctx["css_hash"] = file_hash(SRC / "assets/css/styles.css")
    ctx["js_hash"] = file_hash(SRC / "assets/js/main.js")
    if env == "prod":
        ctx["form_mode"], ctx["form_action"], ctx["form_method"] = "live", "api/send.php", "post"
    else:
        # без JS превью уходит на страницу «спасибо» (на GitHub Pages нет PHP)
        ctx["form_mode"], ctx["form_action"], ctx["form_method"] = "demo", "spasibo/", "get"
    mode = ctx.get("consent_mode", "checkbox")
    if mode not in ("checkbox", "text"):
        raise BuildError(f'consent_mode должен быть "checkbox" или "text", сейчас "{mode}"')
    ctx["consent_checkbox"] = "1" if mode == "checkbox" else ""
    ctx["consent_text"] = "1" if mode == "text" else ""
    ctx["metrika_webvisor_js"] = "true" if cfg.get("metrika_webvisor") else "false"
    ctx["metrika_enabled"] = "1" if env == "prod" and ctx.get("metrika_id") else ""
    # контакты для блока ошибки формы и футера: показываем, если есть хоть один
    ctx["has_messengers"] = "1" if ctx.get("whatsapp_url") or ctx.get("telegram_contact_url") else ""
    return ctx


def check_prod_config(ctx: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for key in REQUIRED_PROD:
        if not ctx.get(key):
            errors.append(f"не заполнен ключ prod.{key} в site.config.json")
    for key in OPTIONAL_PROD:
        if not ctx.get(key):
            warnings.append(f"ключ prod.{key} пустой: связанные элементы вырезаны")
    for key in URL_KEYS:
        if ctx.get(key) == "#":
            errors.append(f'prod.{key} = "#": укажите ссылку или оставьте пустым')
    if ctx.get("metrika_id") and not ctx["metrika_id"].isdigit():
        errors.append("prod.metrika_id должен состоять из цифр (номер счётчика)")
    if ctx.get("site_url") and not ctx["site_url"].startswith("https://"):
        warnings.append("prod.site_url без https://: Директ и Вебмастер ждут HTTPS")
    return errors, warnings


# ---------------------------------------------------------------- шаблоны

INCLUDE_RE = re.compile(r"<!-- include:([\w-]+) -->")
ENV_RE = re.compile(r"<!-- env:(\w+) -->(.*?)<!-- endenv:\1 -->", re.S)
IF_RE = re.compile(r"<!-- if(not)?:(\w+) -->(.*?)<!-- endif:\2 -->", re.S)
IMG_RE = re.compile(r"<!-- img:([\w-]+)((?:\s+[\w-]+(?:=\"[^\"]*\")?)*)\s*-->")
ATTR_RE = re.compile(r"([\w-]+)(?:=\"([^\"]*)\")?")
VAR_RE = re.compile(r"\{\{\s*(\w+)(?:\|(\w+))?\s*\}\}")


def apply_includes(text: str, depth: int = 0) -> str:
    if depth > 5:
        raise BuildError("слишком глубокая вложенность include")

    def repl(m):
        part = SRC / "_partials" / f"{m.group(1)}.html"
        if not part.exists():
            raise BuildError(f"нет файла src/_partials/{m.group(1)}.html")
        return apply_includes(part.read_text(encoding="utf-8").rstrip("\n"), depth + 1)

    return INCLUDE_RE.sub(repl, text)


def apply_env(text: str, env: str) -> str:
    return ENV_RE.sub(lambda m: m.group(2) if m.group(1) == env else "", text)


def apply_ifs(text: str, ctx: dict) -> str:
    def repl(m):
        negate, key, body = m.group(1), m.group(2), m.group(3)
        if key not in ctx:
            raise BuildError(f"if:{key}: такого ключа нет в конфиге")
        truthy = bool(ctx[key])
        return body if truthy != bool(negate) else ""

    prev = None
    while prev != text:  # вложенные блоки с разными ключами
        prev, text = text, IF_RE.sub(repl, text)
    return text


def load_manifest() -> dict:
    path = SRC / "assets/img/manifest.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def render_img(m, root: str, manifest: dict) -> str:
    name = m.group(1)
    attrs = {a.group(1): (a.group(2) if a.group(2) is not None else True)
             for a in ATTR_RE.finditer(m.group(2))}
    if "alt" not in attrs:
        raise BuildError(f"img:{name}: нужен alt")
    alt = html.escape(str(attrs["alt"]), quote=True)
    sizes = attrs.get("sizes", "100vw")
    css = attrs.get("class", "")
    eager = "eager" in attrs
    loading = 'loading="eager" fetchpriority="high"' if eager else 'loading="lazy"'
    info = manifest.get(name)
    if info:
        widths = info["widths"]
        v = f'?v={info["v"]}' if info.get("v") else ""
        webp = ", ".join(f"{root}assets/img/{name}-{w}.webp{v} {w}w" for w in widths)
        jpg = ", ".join(f"{root}assets/img/{name}-{w}.jpg{v} {w}w" for w in widths)
        fallback_w = min(widths, key=lambda w: abs(w - 800))
        return (
            f'<picture>'
            f'<source type="image/webp" srcset="{webp}" sizes="{sizes}">'
            f'<img class="{css}" src="{root}assets/img/{name}-{fallback_w}.jpg{v}" srcset="{jpg}" sizes="{sizes}" '
            f'width="{info["width"]}" height="{info["height"]}" alt="{alt}" {loading} decoding="async">'
            f'</picture>'
        )
    ph = attrs.get("ph", "car")
    ratio = str(attrs.get("ratio", "3:2"))
    rw, rh = (int(x) for x in ratio.split(":"))
    w = 1200
    h = round(w * rh / rw)
    return (
        f'<img class="{css} is-placeholder" src="{root}assets/img/placeholders/{ph}.svg" '
        f'width="{w}" height="{h}" alt="{alt}" {loading} decoding="async" data-placeholder="{name}">'
    )


def apply_vars(text: str, ctx: dict, rel: str) -> str:
    def repl(m):
        key, flt = m.group(1), m.group(2)
        if key not in ctx:
            raise BuildError(f"{rel}: неизвестный ключ {{{{{key}}}}}")
        value = ctx[key]
        if flt == "json":  # строка для JSON-LD без внешних кавычек
            return json.dumps(value, ensure_ascii=False)[1:-1]
        if flt:
            raise BuildError(f"{rel}: неизвестный фильтр |{flt}")
        return value

    return VAR_RE.sub(repl, text)


# ---------------------------------------------------------------- типограф

SKIP_TOKEN_RE = re.compile(
    r"(<!--.*?-->|<(script|style|title|textarea|pre|code)\b.*?</\2\s*>|<[^>]*>)", re.S | re.I
)
SHORT_WORDS = (
    "в|во|к|ко|с|со|у|о|об|обо|и|а|но|да|на|по|до|от|за|из|не|ни|"
    "для|без|под|при|про|над|или"
)
SHORT_RE = re.compile(rf"(?<![\w\-])({SHORT_WORDS}) +(?=\S)", re.I)
DASH_RE = re.compile(r"[ \t]+—(?=\s)")
GROUP_RE = re.compile(r"(\d) (\d{3})(?!\d)")
UNIT_RE = re.compile(r"([\dX]) +(₽|км|дней|дня|день|лет|года|год|%)(?![\w])")
NUMSIGN_RE = re.compile(r"№ +")
RANGE_RE = re.compile(r"(?<![\w\-])(\d+–\d+)(?![\w\-])")
BRAND_RE = re.compile(r"(?<![\w\-])M-AUTO(?![\w\-])")


def typograph_text(s: str, brand_wrap: bool) -> str:
    if not s.strip():
        return s
    s = SHORT_RE.sub(lambda m: m.group(1) + NBSP, s)
    s = DASH_RE.sub(NBSP + "—", s)
    prev = None
    while prev != s:
        prev, s = s, GROUP_RE.sub(lambda m: m.group(1) + NBSP + m.group(2), s)
    s = UNIT_RE.sub(lambda m: m.group(1) + NBSP + m.group(2), s)
    s = NUMSIGN_RE.sub("№" + NBSP, s)
    if brand_wrap:
        # в шрифте нет неразрывного дефиса U+2011, поэтому span
        s = RANGE_RE.sub(r'<span class="nobr">\1</span>', s)
        s = BRAND_RE.sub('<span class="nobr">M-AUTO</span>', s)
    return s


def typograph_html(text: str) -> str:
    parts = SKIP_TOKEN_RE.split(text)
    # split с двумя группами: [text, token, inner-name, text, token, inner-name, ...]
    out = []
    i = 0
    while i < len(parts):
        chunk = parts[i]
        if i % 3 == 0:
            out.append(typograph_text(chunk, brand_wrap=True))
        elif i % 3 == 1:
            out.append(chunk)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------- сборка

def root_prefix(rel: Path) -> str:
    return "../" * (len(rel.parts) - 1)


def should_skip(rel: Path, env: str) -> bool:
    parts = rel.parts
    if parts[0] == "_partials":
        return True
    if rel.name in (".DS_Store", "Thumbs.db", "manifest.json") and "img" in parts:
        return True
    if rel.name in (".DS_Store", "Thumbs.db"):
        return True
    if parts[:3] == ("assets", "img", "raw"):
        return True
    if parts[0] == "api":
        if env == "preview":
            return True
        if rel.name == "config.php":
            return True
        if len(parts) > 2 and parts[1] == "storage" and rel.name != ".htaccess":
            return True
    if env == "preview" and rel.as_posix() in ("sitemap.xml", ".htaccess"):
        return True
    return False


def render_file(text: str, rel: Path, env: str, ctx: dict, manifest: dict) -> str:
    root = root_prefix(rel)
    local = dict(ctx, root=root, home=root or "./")
    text = apply_includes(text)
    text = apply_env(text, env)
    text = apply_ifs(text, local)
    if rel.suffix == ".html":
        text = IMG_RE.sub(lambda m: render_img(m, root, manifest), text)
    text = apply_vars(text, local, rel.as_posix())
    if rel.suffix == ".html":
        # комментарии нужны в исходниках, на сайте это лишний вес и ложные пометки заглушек
        text = re.sub(r"<!--(?!\[if).*?-->", "", text, flags=re.S)
        text = typograph_html(text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def find_placeholders(out: Path) -> list[str]:
    found = []
    for path in sorted(out.rglob("*")):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8").replace(NBSP, " ").replace("&nbsp;", " ")
        text = re.sub(r'<span class="nobr">(.*?)</span>', r"\1", text)
        rel = path.relative_to(out).as_posix()
        for marker in PLACEHOLDER_MARKERS:
            n = text.count(marker)
            if n:
                found.append(f"{rel}: «{marker}» × {n}")
    return found


def build(env: str, allow_placeholders: bool, config_path: Path = CONFIG) -> int:
    cfg = load_config(env, config_path)
    ctx = make_context(cfg, env)
    out = OUT_DIRS[env]

    if env == "prod":
        errors, warnings = check_prod_config(ctx)
        for w in warnings:
            print(f"  предупреждение: {w}")
        if errors and not allow_placeholders:
            raise BuildError("prod-конфиг не заполнен:\n  - " + "\n  - ".join(errors)
                             + "\nЗаполните site.config.json или соберите с --allow-placeholders для теста.")
        for e in errors:
            print(f"  пропущено (--allow-placeholders): {e}")

    manifest = load_manifest()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    count = 0
    for path in sorted(SRC.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(SRC)
        if should_skip(rel, env):
            continue
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if rel.suffix in TEMPLATE_SUFFIXES or rel.name in TEMPLATE_NAMES:
            text = render_file(path.read_text(encoding="utf-8"), rel, env, ctx, manifest)
            dest.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(path, dest)
        count += 1

    if env == "preview":
        (out / ".nojekyll").write_text("", encoding="utf-8")

    placeholders = find_placeholders(out)
    print(f"Сборка {env}: {count} файлов → {out.relative_to(ROOT)}/")
    if placeholders:
        if env == "prod" and not allow_placeholders:
            shutil.rmtree(out)
            raise BuildError("в prod-сборке остались заглушки (см. CONTENT_TO_REPLACE.md):\n  - "
                             + "\n  - ".join(placeholders)
                             + "\nЗамените их или соберите с --allow-placeholders для теста.")
        print(f"  заглушек: {len(placeholders)} мест (нормально для {env}"
              f"{', собрано с --allow-placeholders' if env == 'prod' else ''})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка лендинга M-AUTO")
    parser.add_argument("--env", choices=sorted(OUT_DIRS), required=True)
    parser.add_argument("--allow-placeholders", action="store_true",
                        help="собрать prod, даже если остались заглушки (для теста)")
    parser.add_argument("--config", type=Path, default=CONFIG,
                        help="другой файл конфига (для тестов), по умолчанию site.config.json")
    args = parser.parse_args()
    try:
        return build(args.env, args.allow_placeholders, args.config)
    except BuildError as e:
        print(f"ОШИБКА СБОРКИ: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
