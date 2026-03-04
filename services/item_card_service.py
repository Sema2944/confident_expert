"""Генерация карточки вещи в стиле Pinterest при добавлении в гардероб."""

from __future__ import annotations

from io import BytesIO


class ItemCardService:
    """Рендерит красивую карточку вещи 800×1100px из фото + метаданных AI-анализа."""

    CANVAS_W = 800
    CANVAS_H = 1100
    BG = (250, 247, 242)  # #FAF7F2

    SEASON_ICONS: dict[str, str] = {
        "winter": "❄",
        "demi": "◈",
        "summer": "☀",
        "all": "●",
    }
    SEASON_LABELS: dict[str, str] = {
        "winter": "Зима",
        "demi": "Демисезон",
        "summer": "Лето",
        "all": "Все сезоны",
    }
    FORMALITY_LABELS: dict[str, str] = {
        "casual": "Повседневный",
        "office": "Офисный",
        "smart": "Smart casual",
        "sport": "Спортивный",
    }

    def render_card(
        self,
        photo,
        item_type: str,
        color: str,
        style: str,
        season: str,
    ) -> bytes:
        """Render item card and return JPEG bytes.

        Args:
            photo: PIL Image of the clothing item.
            item_type: Display name, e.g. "👕 Футболка".
            color: Primary color from AI analysis, e.g. "серый".
            style: Formality code from AI analysis, e.g. "casual".
            season: Season code from AI analysis, e.g. "demi".
        """
        from PIL import Image, ImageDraw, ImageFilter, ImageOps

        canvas = Image.new("RGBA", (self.CANVAS_W, self.CANVAS_H), self.BG + (255,))

        # --- Photo zone: 720×720 starting at (40, 40) ---
        ZONE = 720
        ZONE_X, ZONE_Y = 40, 40

        photo_rgba = photo.convert("RGBA")
        fitted = ImageOps.contain(photo_rgba, (ZONE, ZONE), method=Image.Resampling.LANCZOS)
        pw, ph = fitted.size
        px = ZONE_X + (ZONE - pw) // 2
        py = ZONE_Y + (ZONE - ph) // 2

        # Drop shadow
        shadow = Image.new("RGBA", (self.CANVAS_W, self.CANVAS_H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            [px + 4, py + 4, px + pw + 4, py + ph + 4],
            radius=24,
            fill=(0, 0, 0, 70),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        canvas = Image.alpha_composite(canvas, shadow)

        # Rounded corners
        mask = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw, ph], radius=24, fill=255)
        canvas.paste(fitted.convert("RGB"), (px, py), mask)

        # --- Text area ---
        card = canvas.convert("RGB")
        draw = ImageDraw.Draw(card)

        # Separator line
        SEP_Y = 795
        draw.rectangle([40, SEP_Y, self.CANVAS_W - 40, SEP_Y + 2], fill=(200, 168, 130))

        # Fonts
        font_bold = self._load_font(32, bold=True)
        font_body = self._load_font(26)
        font_footer = self._load_font(22)

        TEXT_X = 60
        y = 825

        # Item type (bold)
        type_text = (item_type or "Вещь").strip()
        draw.text((TEXT_X, y), type_text, fill=(26, 26, 26), font=font_bold)
        y += 52

        # Color + style
        color_str = color if color and color not in ("unknown", "") else ""
        style_str = self.FORMALITY_LABELS.get(style or "", "")
        if color_str and style_str:
            chars_line = f"● {color_str} · {style_str}"
        elif color_str:
            chars_line = f"● {color_str}"
        elif style_str:
            chars_line = style_str
        else:
            chars_line = ""
        if chars_line:
            draw.text((TEXT_X, y), chars_line, fill=(107, 101, 96), font=font_body)
        y += 46

        # Season
        s_icon = self.SEASON_ICONS.get(season or "", "")
        s_label = self.SEASON_LABELS.get(season or "", "")
        if s_label:
            season_text = f"{s_icon} {s_label}".strip()
            draw.text((TEXT_X, y), season_text, fill=(107, 101, 96), font=font_body)

        # Footer "──── ШКАФ РАБОТАЕТ ────"
        brand = "ШКАФ РАБОТАЕТ"
        dash = "────"
        try:
            bb = draw.textbbox((0, 0), brand, font=font_footer)
            bw = bb[2] - bb[0]
            db = draw.textbbox((0, 0), dash, font=font_footer)
            dw = db[2] - db[0]
        except Exception:
            bw = len(brand) * 13
            dw = 30

        total_w = dw + 8 + bw + 8 + dw
        fx = (self.CANVAS_W - total_w) // 2
        fy = 1055
        draw.text((fx, fy), dash, fill=(200, 168, 130), font=font_footer)
        draw.text((fx + dw + 8, fy), brand, fill=(155, 149, 144), font=font_footer)
        draw.text((fx + dw + 8 + bw + 8, fy), dash, fill=(200, 168, 130), font=font_footer)

        buf = BytesIO()
        card.save(buf, format="JPEG", quality=92)
        return buf.getvalue()

    @staticmethod
    def _load_font(size: int, bold: bool = False):
        from PIL import ImageFont

        bold_paths = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        )
        regular_paths = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        )
        for path in (bold_paths + regular_paths if bold else regular_paths):
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()
