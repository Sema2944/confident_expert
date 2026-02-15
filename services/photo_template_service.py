cat > services/photo_template_service.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass


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
        from PIL import Image

        template = cls.get_template(template_name)
        canvas = Image.new("RGB", (template.canvas_width, template.canvas_height), color=(255, 255, 255))
        for key, slot in template.slots.items():
            image = photos.get(key)
            if image is None:
                continue
            cls._paste_contained(canvas=canvas, source=image, slot=slot)

        return canvas

    @staticmethod
    def _paste_contained(canvas, source, slot: PhotoSlot) -> None:
        from PIL import Image, ImageOps

        fitted = ImageOps.contain(source, (slot.width, slot.height), method=Image.Resampling.LANCZOS)
        paste_x = slot.x + (slot.width - fitted.width) // 2
        paste_y = slot.y + (slot.height - fitted.height) // 2
        canvas.paste(fitted, (paste_x, paste_y))
PY
