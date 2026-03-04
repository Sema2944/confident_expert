from __future__ import annotations

from dataclasses import dataclass

# Подписи слотов на русском для коллажа
_SLOT_LABELS: dict[str, str] = {
    "top": "верх",
    "bottom": "низ",
    "shoes": "обувь",
    "outerwear": "верхняя одежда",
    "accessories": "аксессуары",
    "accessory": "аксессуары",
    "dress": "платье",
    "headwear": "головной убор",
}


@dataclass(frozen=True)
class PhotoSlot:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class PhotoTemplate:
    canvas_width: int
    canvas_height: int
    slots: dict[str, PhotoSlot]


class PhotoTemplateService:
    """Combines multiple photos into a predefined output format (template)."""

    _TEMPLATES: dict[str, PhotoTemplate] = {
        "outfit_story": PhotoTemplate(
            canvas_width=1536,
            canvas_height=2304,
            slots={
                "outerwear": PhotoSlot(318, 60, 900, 820),
                "top": PhotoSlot(318, 140, 900, 760),
                "dress": PhotoSlot(278, 120, 980, 1520),
                "bottom": PhotoSlot(338, 860, 860, 980),
                "shoes": PhotoSlot(378, 1860, 780, 360),
                "accessories": PhotoSlot(1090, 150, 320, 320),
            },
        ),
        "grid_2x2": PhotoTemplate(
            canvas_width=1400,
            canvas_height=1400,
            slots={
                "slot_1": PhotoSlot(40, 40, 640, 640),
                "slot_2": PhotoSlot(720, 40, 640, 640),
                "slot_3": PhotoSlot(40, 720, 640, 640),
                "slot_4": PhotoSlot(720, 720, 640, 640),
            },
        ),
    }

    @classmethod
    def available_templates(cls) -> tuple[str, ...]:
        return tuple(cls._TEMPLATES.keys())

    @classmethod
    def get_template(cls, template_name: str) -> PhotoTemplate:
        template = cls._TEMPLATES.get(template_name)
        if template is None:
            raise ValueError(f"Unknown template: {template_name}")
        return template

    @classmethod
    def compose(cls, photos: dict[str, object], template_name: str = "outfit_story"):
        """Compose photos into a styled Pinterest-board collage."""
        from PIL import Image, ImageDraw, ImageFilter, ImageOps

        template = cls.get_template(template_name)

        # Expand canvas to fit header and footer
        header_h = 120
        footer_h = 100
        total_h = header_h + template.canvas_height + footer_h

        BG = (250, 247, 242)  # #FAF7F2 warm beige
        canvas = Image.new("RGBA", (template.canvas_width, total_h), BG + (255,))

        # --- Pass 1: collect slot data and draw all shadows at once ---
        shadow_layer = Image.new("RGBA", (template.canvas_width, total_h), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)

        slot_data: list[tuple] = []
        for key, slot in template.slots.items():
            img = photos.get(key)
            if img is None:
                continue
            img_rgba = img.convert("RGBA") if hasattr(img, "convert") else img
            fitted = ImageOps.contain(img_rgba, (slot.width, slot.height), method=Image.Resampling.LANCZOS)
            pw, ph = fitted.size
            px = slot.x + (slot.width - pw) // 2
            py = slot.y + header_h + (slot.height - ph) // 2
            label = _SLOT_LABELS.get(key)
            slot_data.append((fitted, px, py, pw, ph, label))

            shadow_draw.rounded_rectangle(
                [px + 4, py + 4, px + pw + 4, py + ph + 4],
                radius=24,
                fill=(0, 0, 0, 70),
            )

        # Blur all shadows together for soft look
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(10))
        canvas = Image.alpha_composite(canvas, shadow_layer)

        # --- Pass 2: paste photos with rounded corners ---
        for fitted, px, py, pw, ph, label in slot_data:
            mask = Image.new("L", (pw, ph), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw, ph], radius=24, fill=255)
            canvas.paste(fitted.convert("RGB"), (px, py), mask)

        # --- Text layer ---
        card = canvas.convert("RGB")
        draw = ImageDraw.Draw(card)

        font_label = cls._load_font(28)
        font_title = cls._load_font(36)
        font_footer = cls._load_font(24)

        # Category labels below each photo
        for _, px, py, pw, ph, label in slot_data:
            if not label:
                continue
            try:
                bbox = draw.textbbox((0, 0), label, font=font_label)
                lw = bbox[2] - bbox[0]
                draw.text((px + (pw - lw) // 2, py + ph + 8), label, fill=(107, 101, 96), font=font_label)
            except Exception:
                draw.text((px, py + ph + 8), label, fill=(107, 101, 96), font=font_label)

        # Header: title
        title = "ШКАФ РАБОТАЕТ"
        try:
            bbox = draw.textbbox((0, 0), title, font=font_title)
            tw = bbox[2] - bbox[0]
            draw.text(((template.canvas_width - tw) // 2, 32), title, fill=(26, 26, 26), font=font_title)
        except Exception:
            draw.text((template.canvas_width // 4, 32), title, fill=(26, 26, 26), font=font_title)

        # Header: decorative line
        line_w = 120
        lx = (template.canvas_width - line_w) // 2
        draw.rectangle([lx, 84, lx + line_w, 86], fill=(200, 168, 130))

        # Footer
        footer_text = "@shkaf_rabotaet · AI-стилист"
        try:
            bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
            fw = bbox[2] - bbox[0]
            fh = bbox[3] - bbox[1]
            fx = (template.canvas_width - fw) // 2
            fy = header_h + template.canvas_height + (footer_h - fh) // 2
            draw.text((fx, fy), footer_text, fill=(155, 149, 144), font=font_footer)
        except Exception:
            draw.text((template.canvas_width // 4, header_h + template.canvas_height + 40),
                      footer_text, fill=(155, 149, 144), font=font_footer)

        return card

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

    @staticmethod
    def _paste_contained(canvas, source, slot: PhotoSlot) -> None:
        """Legacy: paste without styling. Kept for backward compatibility."""
        from PIL import Image, ImageOps

        fitted = ImageOps.contain(source, (slot.width, slot.height), method=Image.Resampling.LANCZOS)
        paste_x = slot.x + (slot.width - fitted.width) // 2
        paste_y = slot.y + (slot.height - fitted.height) // 2
        canvas.paste(fitted, (paste_x, paste_y))

    @staticmethod
    def _paste_styled(canvas, source, slot: PhotoSlot, label: str | None = None) -> None:
        """Paste with rounded corners (radius=24), drop shadow, and optional label."""
        from PIL import Image, ImageDraw, ImageFilter, ImageOps

        fitted = ImageOps.contain(source.convert("RGBA"), (slot.width, slot.height), method=Image.Resampling.LANCZOS)
        pw, ph = fitted.size
        px = slot.x + (slot.width - pw) // 2
        py = slot.y + (slot.height - ph) // 2
        radius = 24

        # Shadow
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            [px + 4, py + 4, px + pw + 4, py + ph + 4], radius=radius, fill=(0, 0, 0, 70)
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        canvas_rgba = Image.alpha_composite(canvas.convert("RGBA"), shadow)

        # Rounded photo
        mask = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw, ph], radius=radius, fill=255)
        canvas_rgba.paste(fitted.convert("RGB"), (px, py), mask)
        canvas.paste(canvas_rgba.convert("RGB"), (0, 0))

        # Label
        if label:
            draw = ImageDraw.Draw(canvas)
            from PIL import ImageFont
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
            except (OSError, IOError):
                font = ImageFont.load_default()
            try:
                bbox = draw.textbbox((0, 0), label, font=font)
                lw = bbox[2] - bbox[0]
                draw.text((px + (pw - lw) // 2, py + ph + 8), label, fill=(107, 101, 96), font=font)
            except Exception:
                draw.text((px, py + ph + 8), label, fill=(107, 101, 96), font=font)
