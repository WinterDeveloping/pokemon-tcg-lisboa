"""Render the event list as a PNG poster that drops straight into a Discord chat."""

from datetime import date
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from events import Event

WIDTH = 1000
PAD = 44
ROW_H = 88
ICON = 60
HEADER_H = 150
MONTH_H = 58
FOOTER_H = 64

BG = (17, 19, 26)
CARD = (26, 29, 39)
CARD_ALT = (31, 35, 46)
TEXT = (238, 240, 246)
MUTED = (138, 146, 166)
ACCENT = (255, 203, 5)   # Pokemon yellow
# League Cups outrank Challenges, so the Cup gets the bright accent and a
# tinted row while the Challenge recedes to a neutral slate.
CUP = (125, 211, 252)          # light blue
CUP_BG = (24, 41, 56)          # blue-tinted row
CUP_EDGE = (54, 88, 116)
CHALLENGE = (116, 126, 148)    # muted slate
PRERELEASE = (167, 139, 250)

# Official Play! Pokemon event badges, mirrored from pokedata.ovh.
ICON_DIR = Path(__file__).with_name("icons")
ICON_FILES = {
    "League Cup": "cup.png",
    "League Challenge": "chall.png",
    "Pre-Release": "pre.png",
}
BAR_COLORS = {
    "League Cup": CUP,
    "League Challenge": CHALLENGE,
    "Pre-Release": PRERELEASE,
}

FONT_DIR = Path("C:/Windows/Fonts")
MONTHS_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
WEEKDAYS_PT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONT_DIR / name), size)
    except OSError:
        return ImageFont.load_default(size)


@lru_cache(maxsize=8)
def _icon(label: str, size: int) -> Image.Image | None:
    """Badge for an event type, or None if the file is missing."""
    filename = ICON_FILES.get(label)
    if not filename:
        return None
    path = ICON_DIR / filename
    if not path.exists():
        return None
    return Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)


def _text_pill(draw, xy, text, color, font) -> float:
    """Fallback badge used when the icon PNGs are unavailable."""
    x, y = xy
    w = draw.textlength(text, font=font) + 24
    tint = tuple(int(c * 0.28 + b * 0.72) for c, b in zip(color, CARD))
    draw.rounded_rectangle([x, y, x + w, y + 28], radius=14, fill=tint)
    draw.text((x + 12, y + 14), text, font=font, fill=color, anchor="lm")
    return w


def render(events: list[Event], out_path: Path, radius_km: float = 30.0) -> Path:
    f_title = _font("seguibl.ttf", 40)
    f_sub = _font("segoeui.ttf", 20)
    f_month = _font("segoeuib.ttf", 22)
    f_day = _font("segoeuib.ttf", 28)
    f_dow = _font("segoeui.ttf", 15)
    f_shop = _font("segoeuib.ttf", 23)
    f_meta = _font("segoeui.ttf", 17)
    f_pill = _font("seguisb.ttf", 15)
    f_foot = _font("segoeui.ttf", 15)

    # Group by month so the poster stays readable when the list runs long.
    groups: dict[tuple[int, int], list[Event]] = {}
    for event in events:
        groups.setdefault((event.date.year, event.date.month), []).append(event)

    height = HEADER_H + FOOTER_H + sum(MONTH_H + len(v) * ROW_H for v in groups.values()) + PAD
    image = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(image)

    # Header
    draw.rectangle([0, 0, WIDTH, 6], fill=ACCENT)
    draw.text((PAD, 46), "Pokémon TCG · Lisboa", font=f_title, fill=TEXT)
    draw.text((PAD, 98), f"Cups, Challenges e Pre-Releases · até {radius_km:.0f} km do centro",
              font=f_sub, fill=MUTED)

    y = HEADER_H
    for (year, month), items in groups.items():
        draw.text((PAD, y + MONTH_H / 2), f"{MONTHS_PT[month - 1].upper()} {year}",
                  font=f_month, fill=ACCENT, anchor="lm")
        y += MONTH_H

        for i, event in enumerate(items):
            card_h = ROW_H - 8
            is_cup = event.label == "League Cup"
            colour = BAR_COLORS.get(event.label, MUTED)

            if is_cup:
                draw.rounded_rectangle([PAD, y, WIDTH - PAD, y + card_h], radius=10,
                                       fill=CUP_BG, outline=CUP_EDGE, width=1)
            else:
                row_bg = CARD if i % 2 == 0 else CARD_ALT
                draw.rounded_rectangle([PAD, y, WIDTH - PAD, y + card_h], radius=10, fill=row_bg)

            bar_w = 8 if is_cup else 4
            draw.rounded_rectangle([PAD, y, PAD + bar_w, y + card_h], radius=3, fill=colour)

            # Date block
            cx = PAD + 48
            draw.text((cx, y + 30), f"{event.date.day:02d}", font=f_day,
                      fill=(CUP if is_cup else TEXT), anchor="mm")
            draw.text((cx, y + 57), WEEKDAYS_PT[event.date.weekday()], font=f_dow, fill=MUTED, anchor="mm")

            # Official event badge, with a text pill as fallback.
            icon = _icon(event.label, ICON)
            text_x = PAD + 96
            if icon is not None:
                image.paste(icon, (text_x, y + (card_h - ICON) // 2), icon)
                text_x += ICON + 18
            else:
                text_x += _text_pill(draw, (text_x, y + 12), event.label, colour, f_pill) + 14

            draw.text((text_x, y + 32), event.shop, font=f_shop,
                      fill=(CUP if is_cup else TEXT), anchor="lm")

            meta = f"{event.city} · {event.km:.0f} km"
            if event.time:
                meta += f" · {event.time}"
            if event.cost:
                meta += f" · {event.cost}"
            draw.text((text_x, y + 58), meta, font=f_meta, fill=MUTED, anchor="lm")

            y += ROW_H

    footer = f"Fonte: pokedata.ovh · gerado {date.today():%d/%m/%Y} · {len(events)} eventos"
    draw.text((PAD, height - FOOTER_H / 2), footer, font=f_foot, fill=MUTED, anchor="lm")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, "PNG", optimize=True)
    return out_path
