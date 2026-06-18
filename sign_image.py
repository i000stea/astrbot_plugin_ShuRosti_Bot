import os
import time
from typing import Optional

_IMG_DIR = os.path.join(os.path.dirname(__file__), "data", "sign_images")

_RARITY_COLORS = {
    1: (180, 180, 180),
    2: (100, 200, 100),
    3: (80, 160, 220),
    4: (160, 100, 220),
    5: (220, 170, 50),
}
_BG = (18, 18, 24)
_CARD_BG = (30, 30, 40)
_CARD_SIGNED = (28, 60, 38)
_CARD_BORDER = (60, 60, 80)
_CARD_SIGNED_BORDER = (60, 160, 80)
_WHITE = (240, 240, 240)
_GRAY = (140, 140, 160)
_ACCENT = (100, 180, 255)
_GOLD = (220, 170, 50)

_COLS = 7
_CARD_W = 110
_CARD_H = 130
_PAD = 16
_HEADER_H = 72
_FOOTER_H = 40


def _try_pil():
    try:
        from PIL import Image, ImageDraw, ImageFont
        return Image, ImageDraw, ImageFont
    except ImportError:
        return None, None, None


def _load_font(ImageFont, size: int):
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _round_rect(draw, xy, radius, fill, outline, outline_width=2):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=outline, width=outline_width)


def _cache_path(year: int, month: int, qq_id: str) -> str:
    os.makedirs(_IMG_DIR, exist_ok=True)
    return os.path.join(_IMG_DIR, f"{qq_id}_{year}_{month:02d}.png")


def cached_image_path(qq_id: str) -> Optional[str]:
    t = time.localtime()
    path = _cache_path(t.tm_year, t.tm_mon, qq_id)
    return path if os.path.exists(path) else None


def generate_monthly_image(sign_list: list[dict], qq_id: str) -> Optional[str]:
    Image, ImageDraw, ImageFont = _try_pil()
    if Image is None:
        return None

    t = time.localtime()
    path = _cache_path(t.tm_year, t.tm_mon, qq_id)

    days = len(sign_list)
    if days == 0:
        return None

    rows = (days + _COLS - 1) // _COLS
    img_w = _COLS * _CARD_W + (_COLS + 1) * _PAD
    img_h = _HEADER_H + rows * _CARD_H + (rows + 1) * _PAD + _FOOTER_H

    img = Image.new("RGB", (img_w, img_h), _BG)
    draw = ImageDraw.Draw(img)

    font_title = _load_font(ImageFont, 22)
    font_day = _load_font(ImageFont, 14)
    font_item = _load_font(ImageFont, 12)
    font_count = _load_font(ImageFont, 11)
    font_footer = _load_font(ImageFont, 11)

    title = f"{t.tm_year}年{t.tm_mon}月 签到奖励一览"
    draw.text((_PAD, 18), title, font=font_title, fill=_ACCENT)
    signed_count = sum(1 for d in sign_list if d.get("isSign", False))
    sub = f"已签到 {signed_count} / {days} 天"
    draw.text((_PAD, 46), sub, font=font_day, fill=_GRAY)

    for idx, day_info in enumerate(sign_list):
        col = idx % _COLS
        row = idx // _COLS
        x0 = _PAD + col * (_CARD_W + _PAD)
        y0 = _HEADER_H + _PAD + row * (_CARD_H + _PAD)
        x1 = x0 + _CARD_W
        y1 = y0 + _CARD_H

        is_signed = day_info.get("isSign", False)
        bg = _CARD_SIGNED if is_signed else _CARD_BG
        border = _CARD_SIGNED_BORDER if is_signed else _CARD_BORDER
        _round_rect(draw, (x0, y0, x1, y1), 8, bg, border)

        day_num = idx + 1
        day_label = f"第{day_num}天"
        draw.text((x0 + 8, y0 + 6), day_label, font=font_day, fill=_WHITE if is_signed else _GRAY)

        if is_signed:
            draw.text((x1 - 22, y0 + 6), "✓", font=font_day, fill=_CARD_SIGNED_BORDER)

        resources = day_info.get("resourceList", [])
        if not resources:
            draw.text((x0 + 8, y0 + 36), "—", font=font_item, fill=_GRAY)
        else:
            item_y = y0 + 30
            for res in resources[:3]:
                name = res.get("name", "")
                count = res.get("count", 0)
                rarity = res.get("rarity", 1)
                color = _RARITY_COLORS.get(rarity, _WHITE)

                max_chars = 8
                if len(name) > max_chars:
                    name = name[:max_chars - 1] + "…"
                draw.text((x0 + 8, item_y), name, font=font_item, fill=color)
                item_y += 18
                draw.text((x0 + 8, item_y), f"×{count}", font=font_count, fill=_GOLD)
                item_y += 16
                if item_y + 16 > y1 - 4:
                    break

    gen_time = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    footer_text = f"每月仅生成一次 · 生成于 {gen_time}"
    draw.text((_PAD, img_h - _FOOTER_H + 12), footer_text, font=font_footer, fill=_GRAY)

    img.save(path, "PNG", optimize=True)
    return path


def format_rewards_text(sign_list: list[dict]) -> str:
    t = time.localtime()
    lines = [f"📅 {t.tm_year}年{t.tm_mon}月签到奖励\n"]
    signed_count = sum(1 for d in sign_list if d.get("isSign", False))
    lines.append(f"已签 {signed_count}/{len(sign_list)} 天\n")
    for idx, day_info in enumerate(sign_list):
        is_signed = day_info.get("isSign", False)
        mark = "✅" if is_signed else "⬜"
        resources = day_info.get("resourceList", [])
        items = "、".join(
            f"{r.get('name', '')}×{r.get('count', 0)}" for r in resources
        )
        lines.append(f"{mark} 第{idx + 1:2d}天：{items or '—'}")
    return "\n".join(lines)
