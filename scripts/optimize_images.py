#!/usr/bin/env python3
"""Оптимизация картинок для лендинга M-AUTO (нужен Pillow).

    python3 scripts/optimize_images.py           # raw/ → WebP + JPEG + manifest.json
    python3 scripts/optimize_images.py --icons   # favicon.ico, apple-touch-icon.png, og-image.jpg

Исходники кладутся в src/assets/img/raw/ с именами из CONTENT_TO_REPLACE.md:
hero.jpg, case-1.jpg … case-6.jpg, client-1.jpg … client-3.jpg, og.jpg.
Имя файла = имя в макросе <!-- img:… --> в index.html. После оптимизации
запустите build.py: вместо SVG-заглушки встанет <picture> с srcset.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "src/assets/img/raw"
OUT = ROOT / "src/assets/img"
MANIFEST = OUT / "manifest.json"
FONT = ROOT / "scripts/fonts/Onest-wght.ttf"

WIDTHS = [480, 800, 1200, 1600]
HERO_WIDTHS = WIDTHS + [1920]
QUALITY = 78
SOURCE_EXT = {".jpg", ".jpeg", ".png", ".webp"}

GRAPHITE = (36, 40, 44)
WHITE = (255, 255, 255)
MUTED_ON_DARK = (185, 190, 195)


def optimize_one(src: Path) -> dict:
    name = src.stem.lower()
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        widths = HERO_WIDTHS if name == "hero" else WIDTHS
        usable = [w for w in widths if w <= im.width] or [im.width]
        for w in usable:
            h = round(im.height * w / im.width)
            resized = im.resize((w, h), Image.LANCZOS)
            resized.save(OUT / f"{name}-{w}.webp", "WEBP", quality=QUALITY, method=6)
            resized.save(OUT / f"{name}-{w}.jpg", "JPEG", quality=QUALITY, optimize=True, progressive=True)
        largest = usable[-1]
        info = {
            "widths": usable,
            "width": largest,
            "height": round(im.height * largest / im.width),
            "v": hashlib.sha256(src.read_bytes()).hexdigest()[:8],
        }
    sizes = ", ".join(f"{w}: {(OUT / f'{name}-{w}.webp').stat().st_size // 1024} КБ" for w in usable)
    print(f"{src.name} → {name}-*.webp/jpg ({sizes})")
    return info


def make_og_from_photo(src: Path) -> None:
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        og = ImageOps.fit(im, (1200, 630), Image.LANCZOS)
        og.save(ROOT / "src/og-image.jpg", "JPEG", quality=82, optimize=True, progressive=True)
    print(f"{src.name} → src/og-image.jpg (1200×630)")


def optimize() -> int:
    if not RAW.exists():
        RAW.mkdir(parents=True)
        print(f"Создана папка {RAW.relative_to(ROOT)}: положите туда фото и запустите снова.")
        return 0
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    sources = sorted(p for p in RAW.iterdir() if p.suffix.lower() in SOURCE_EXT)
    if not sources:
        print("В raw/ нет фото (jpg, png, webp).")
        return 0
    for src in sources:
        if src.stem.lower() == "og":
            make_og_from_photo(src)
            continue
        manifest[src.stem.lower()] = optimize_one(src)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manifest.json: {len(manifest)} картинок. Теперь запустите scripts/build.py.")
    return 0


# ---------------------------------------------------------------- иконки и OG-заглушка

def font(size: int, weight: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT), size)
    try:
        f.set_variation_by_axes([weight])
    except (OSError, AttributeError):
        pass  # FreeType без вариативных шрифтов: останется Regular
    return f


def monogram(size: int, rounded: bool) -> Image.Image:
    """Монограмма M: белая линия на графите, как в favicon.svg."""
    scale = 4  # рисуем крупнее и уменьшаем: ровные края
    s = size * scale
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if rounded:
        d.rounded_rectangle((0, 0, s - 1, s - 1), radius=round(s * 0.1875), fill=GRAPHITE)
    else:
        d.rectangle((0, 0, s, s), fill=GRAPHITE)
    u = s / 64
    pts = [(18 * u, 46 * u), (18 * u, 18 * u), (32 * u, 36 * u), (46 * u, 18 * u), (46 * u, 46 * u)]
    d.line(pts, fill=WHITE, width=round(6 * u), joint="curve")
    r = 3 * u  # круглые концы
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=WHITE)
    return im.resize((size, size), Image.LANCZOS)


def og_placeholder() -> None:
    im = Image.new("RGB", (1200, 630), GRAPHITE)
    d = ImageDraw.Draw(im)
    d.text((80, 72), "M-AUTO", font=font(34, 620), fill=WHITE)
    title = font(64, 560)
    lines = ["Авто из Германии и Европы —", "с полной проверкой", "и фиксированной ценой"]
    y = 210
    for line in lines:
        d.text((80, y), line, font=title, fill=WHITE)
        y += 78
    d.text((80, 520), "Подбор, проверка и доставка по всей России", font=font(30, 400), fill=MUTED_ON_DARK)
    im.save(ROOT / "src/og-image.jpg", "JPEG", quality=86, optimize=True, progressive=True)
    print("src/og-image.jpg: типографская заглушка 1200×630")


def icons(force_og: bool) -> int:
    ico = monogram(64, rounded=True)
    ico.save(ROOT / "src/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    touch = monogram(180, rounded=False).convert("RGB")
    touch.save(ROOT / "src/apple-touch-icon.png", optimize=True)
    print("src/favicon.ico (16, 32, 48), src/apple-touch-icon.png (180×180)")
    og_raw = next((p for p in RAW.glob("og.*") if p.suffix.lower() in SOURCE_EXT), None) if RAW.exists() else None
    if og_raw:
        make_og_from_photo(og_raw)
    elif force_og or not (ROOT / "src/og-image.jpg").exists():
        og_placeholder()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Оптимизация картинок M-AUTO")
    parser.add_argument("--icons", action="store_true", help="фавиконки и og-image.jpg")
    parser.add_argument("--og", action="store_true", help="перерисовать OG-заглушку")
    args = parser.parse_args()
    if args.icons:
        return icons(args.og)
    return optimize()


if __name__ == "__main__":
    sys.exit(main())
