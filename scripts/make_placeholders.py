#!/usr/bin/env python3
"""Генерирует SVG-заглушки: светло-серая плашка с тонким силуэтом авто.

    python3 scripts/make_placeholders.py   → src/assets/img/placeholders/*.svg

Нужны, пока нет реальных фото. Когда фото появятся, макрос img в build.py
сам подставит <picture> вместо заглушки.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src/assets/img/placeholders"

STROKE = "#9aa1a8"
GROUND = "#d3d7db"

# Профили в координатах: x 0..1000 (нос справа), y вверх от земли.
# body: верхний контур от заднего низа к переднему низу; win: окна;
# wheels: центры колёс; r: радиус колеса; clear: высота нижней линии.
CARS = {
    "hatch": dict(
        body=[(50, 70), (40, 150), (58, 236), (130, 292), (290, 300), (400, 290), (500, 214),
              (660, 188), (738, 166), (752, 74)],
        win=[(104, 230), (150, 278), (290, 286), (392, 278), (470, 216)],
        wheels=(180, 620), r=72, clear=52, length=790,
    ),
    "crossover": dict(
        body=[(40, 86), (30, 170), (44, 262), (110, 318), (330, 332), (560, 326), (690, 238),
              (880, 212), (958, 182), (968, 90)],
        win=[(96, 254), (136, 304), (330, 316), (550, 312), (650, 240)],
        wheels=(210, 770), r=88, clear=70, length=1000,
    ),
    "sedan": dict(
        body=[(30, 64), (20, 122), (30, 176), (140, 196), (260, 204), (380, 290), (570, 296),
              (712, 208), (900, 178), (976, 152), (986, 70)],
        win=[(290, 206), (390, 280), (565, 284), (680, 210)],
        wheels=(205, 790), r=76, clear=54, length=1000,
    ),
    "wagon": dict(
        body=[(30, 66), (22, 140), (30, 240), (70, 290), (300, 296), (560, 292), (712, 210),
              (900, 180), (976, 154), (986, 72)],
        win=[(70, 222), (100, 276), (300, 282), (555, 280), (680, 212)],
        wheels=(205, 790), r=76, clear=54, length=1000,
    ),
    "suv": dict(
        body=[(30, 92), (24, 200), (30, 300), (60, 352), (360, 362), (600, 358), (700, 262),
              (900, 246), (968, 226), (974, 96)],
        win=[(66, 270), (88, 336), (360, 346), (590, 342), (672, 266)],
        wheels=(215, 780), r=94, clear=78, length=1000,
    ),
    "ev": dict(
        body=[(36, 66), (28, 126), (44, 190), (180, 236), (380, 296), (560, 300), (700, 228),
              (880, 186), (968, 150), (980, 72)],
        win=[(200, 230), (390, 284), (555, 288), (670, 228)],
        wheels=(215, 785), r=78, clear=52, length=1000,
    ),
}


def catmull_rom(points):
    """Гладкая кривая через точки (Catmull-Rom → кубические Безье)."""
    pts = list(points)
    if len(pts) < 3:
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    n = len(pts)
    for i in range(n - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < n else p2
        t = 0.16
        c1 = (p1[0] + (p2[0] - p0[0]) * t, p1[1] + (p2[1] - p0[1]) * t)
        c2 = (p2[0] - (p3[0] - p1[0]) * t, p2[1] - (p3[1] - p1[1]) * t)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def car_paths(spec, ox, oy, scale):
    """Возвращает SVG-элементы силуэта. ox, oy: точка земли под задом авто."""
    def tr(p):
        return (ox + p[0] * scale, oy - p[1] * scale)

    body = [tr(p) for p in spec["body"]]
    r = spec["r"] * scale
    arch = r * 1.17
    clear_y = oy - spec["clear"] * scale
    rear_c, front_c = (tr((spec["wheels"][0], spec["r"])), tr((spec["wheels"][1], spec["r"])))

    # верх: от заднего низа к переднему низу
    d = catmull_rom(body)

    # низ: от переднего низа назад, с арками
    def arch_x(c):
        dy = clear_y - c[1]
        dx = (arch ** 2 - dy ** 2) ** 0.5
        return c[0] + dx, c[0] - dx

    f_right, f_left = arch_x(front_c)
    r_right, r_left = arch_x(rear_c)
    d += f" L{f_right:.1f},{clear_y:.1f}"
    d += f" A{arch:.1f},{arch:.1f} 0 0 0 {f_left:.1f},{clear_y:.1f}"
    d += f" L{r_right:.1f},{clear_y:.1f}"
    d += f" A{arch:.1f},{arch:.1f} 0 0 0 {r_left:.1f},{clear_y:.1f}"
    d += " Z"

    win = catmull_rom([tr(p) for p in spec["win"]]) + " Z"
    els = [f'<path d="{d}"/>', f'<path d="{win}"/>']
    for c in (rear_c, front_c):
        els.append(f'<circle cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="{r:.1f}"/>')
        els.append(f'<circle cx="{c[0]:.1f}" cy="{c[1]:.1f}" r="{r * 0.42:.1f}"/>')
    return els


def svg(width, height, inner, ground=None):
    g = ""
    if ground:
        x1, x2, y = ground
        g = f'<path d="M{x1:.1f},{y:.1f} H{x2:.1f}" stroke="{GROUND}"/>'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}">'
        f'<style>path,circle{{vector-effect:non-scaling-stroke}}</style>'
        f'<g fill="none" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round">{g}'
        f'<g stroke="{STROKE}">{"".join(inner)}</g></g></svg>\n'
    )


def car_svg(name, width, height, fill=0.68):
    spec = CARS[name]
    scale = width * fill / spec["length"]
    car_w = spec["length"] * scale
    ox = (width - car_w) / 2
    car_h = max(p[1] for p in spec["body"]) * scale
    oy = height / 2 + car_h / 2
    els = car_paths(spec, ox, oy, scale)
    return svg(width, height, els, ground=(ox - car_w * 0.06, ox + car_w * 1.06, oy))


def client_svg(width=1200, height=800):
    """Человек рядом с авто: заглушка под фото клиента."""
    spec = CARS["crossover"]
    scale = width * 0.52 / spec["length"]
    car_w = spec["length"] * scale
    ox = width * 0.36
    oy = height * 0.72
    els = car_paths(spec, ox, oy, scale)
    px = width * 0.24
    head_r = height * 0.045
    body_h = height * 0.36
    top = oy - body_h - head_r * 2.4
    els.append(f'<circle cx="{px:.1f}" cy="{top + head_r:.1f}" r="{head_r:.1f}"/>')
    shoulders = top + head_r * 2.5
    w = head_r * 1.9
    els.append(
        f'<path d="M{px - w:.1f},{oy:.1f} V{shoulders + w:.1f} '
        f'Q{px - w:.1f},{shoulders:.1f} {px:.1f},{shoulders:.1f} '
        f'Q{px + w:.1f},{shoulders:.1f} {px + w:.1f},{shoulders + w:.1f} V{oy:.1f}"/>'
    )
    return svg(width, height, els, ground=(px - w * 2, ox + car_w * 1.05, oy))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = {f"car-{n}.svg": car_svg(n, 1200, 900) for n in CARS}
    files["hero.svg"] = car_svg("crossover", 1200, 900, fill=0.72)
    files["client.svg"] = client_svg()
    for fname, content in files.items():
        (OUT / fname).write_text(content, encoding="utf-8")
        print(f"{fname}: {len(content)} байт")


if __name__ == "__main__":
    main()
