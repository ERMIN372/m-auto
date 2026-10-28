#!/usr/bin/env python3
"""Разовая нарезка шрифта: Onest variable → src/assets/fonts/onest-var.woff2.

Нужен fonttools + brotli только на машине разработчика:
    pip install fonttools brotli
    python3 scripts/subset_font.py

Ось wght урезается до 400–650 (больше на сайте не используется),
глифы: латиница, кириллица, типографские знаки, ₽ и №.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_FONT = ROOT / "scripts/fonts/Onest-wght.ttf"
OUT = ROOT / "src/assets/fonts/onest-var.woff2"
UNICODES = ",".join([
    "U+0020-007E", "U+00A0-00BB", "U+00D7", "U+0400-045F", "U+0490-0491",
    "U+2009", "U+2013", "U+2014", "U+2018-201E", "U+2026",
    "U+20BD", "U+2116", "U+2190-2193", "U+2212",
])


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        limited = Path(tmp) / "onest-limited.ttf"
        subprocess.run([sys.executable, "-m", "fontTools.varLib.instancer", str(SRC_FONT),
                        "wght=400:650", "-o", str(limited)], check=True)
        subprocess.run([sys.executable, "-m", "fontTools.subset", str(limited),
                        f"--unicodes={UNICODES}",
                        "--layout-features=kern,liga,calt,locl,tnum,lnum,case",
                        "--flavor=woff2", f"--output-file={OUT}"], check=True)
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size // 1024} КБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
