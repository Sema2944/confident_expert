from io import BytesIO
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OutfitResult:
    description: str
    items: dict
    image_prompt: str


class OutfitService:
    _IMAGE_PROMPT_TEMPLATE = Path(__file__).resolve().parents[1] / "prompts" / "image_generation.txt"

    @staticmethod
    def _pick_with_offset(values: list[dict], offset: int) -> dict | None:
        if not values:
            return None
        return values[offset % len(values)]

    @staticmethod
    def _item_descriptor(item: dict | None, fallback: str) -> str:
        if not item:
            return "none"

        primary_color = (item.get("primary_color") or "").strip().lower()
        item_type = (item.get("type") or "").strip().lower()

        if primary_color in {"unknown", "none", "null", "-"}:
            primary_color = ""
        if item_type in {"unknown", "none", "null", "-"}:
            item_type = ""

        if primary_color and item_type:
            return f"{primary_color} {item_type}"
        if item_type:
            return item_type
        if primary_color:
            return f"{primary_color} {fallback}"
        return fallback

    @classmethod
    def _build_image_prompt(
        cls,
        top: dict | None,
        bottom: dict | None,
        dress: dict | None,
        outerwear: dict | None,
        shoes: dict | None,
        accessory: dict | None,
    ) -> str:
        top_desc = cls._item_descriptor(top, "top")
        bottom_desc = cls._item_descriptor(bottom, "bottom")
        dress_desc = cls._item_descriptor(dress, "dress")
        outerwear_desc = cls._item_descriptor(outerwear, "outerwear")
        shoes_desc = cls._item_descriptor(shoes, "shoes")
        accessories_desc = cls._item_descriptor(accessory, "accessory")

        template = cls._IMAGE_PROMPT_TEMPLATE.read_text(encoding="utf-8")
        prompt = template.format(
            top_desc=top_desc,
            bottom_desc=bottom_desc,
            dress_desc=dress_desc,
            outerwear_desc=outerwear_desc,
            shoes_desc=shoes_desc,
            accessories_desc=accessories_desc,
        )

        normalized_prompt = (
            prompt.replace("SYSTEM:", "")
            .replace("USER:", "")
            .replace("\n", " ")
            .strip()
        )
        return " ".join(normalized_prompt.split())

    async def generate_outfits(
        self,
        items: list[dict],
        occasion: str,
        season: str,
        count: int,
    ) -> list[OutfitResult]:
        grouped: dict[str, list[dict]] = {}
        for item in items:
            category = item.get("category")
            if not category:
                continue
            grouped.setdefault(category, []).append(item)

        tops = grouped.get("top", [])
        bottoms = grouped.get("bottom", [])
        dresses = grouped.get("onepiece", [])
        outerwears = grouped.get("outerwear", [])
        shoes = grouped.get("shoes", [])
        accessories = grouped.get("accessory", [])

        if not shoes:
            return []

        results: list[OutfitResult] = []
        for index in range(count):
            use_dress = bool(dresses and (not tops or not bottoms or index % 2 == 1))

            top = None if use_dress else self._pick_with_offset(tops, index)
            bottom = None if use_dress else self._pick_with_offset(bottoms, index)
            dress = self._pick_with_offset(dresses, index) if use_dress else None

            if use_dress and not dress:
                continue
            if not use_dress and (not top or not bottom):
                continue

            shoe = self._pick_with_offset(shoes, index)
            outerwear = self._pick_with_offset(outerwears, index) if outerwears else None
            accessory = self._pick_with_offset(accessories, index) if accessories else None

            items_payload = {
                "top": [top["telegram_file_id"]] if top else [],
                "bottom": [bottom["telegram_file_id"]] if bottom else [],
                "dress": [dress["telegram_file_id"]] if dress else [],
                "outerwear": [outerwear["telegram_file_id"]] if outerwear else [],
                "shoes": [shoe["telegram_file_id"]] if shoe else [],
                "accessories": [accessory["telegram_file_id"]] if accessory else [],
            }

            description = (
                f"Образ #{index + 1}: {occasion}, {season}. "
                f"{'Платье + обувь' if use_dress else 'Верх + низ + обувь'}"
                f"{' + верхняя одежда' if outerwear else ''}"
                f"{' + аксессуары' if accessory else ''}."
            )

            image_prompt = self._build_image_prompt(
                top=top,
                bottom=bottom,
                dress=dress,
                outerwear=outerwear,
                shoes=shoe,
                accessory=accessory,
            )

            results.append(
                OutfitResult(
                    description=description,
                    items=items_payload,
                    image_prompt=image_prompt,
                )
            )

        return results


class OutfitImageService:
    _CATEGORY_ORDER = ["top", "bottom", "dress", "outerwear", "shoes", "accessories"]

    async def render_outfit_image(self, bot, items_payload: dict[str, list[str]]) -> bytes | None:
        from PIL import Image

        file_ids: list[str] = []
        for category in self._CATEGORY_ORDER:
            file_ids.extend(items_payload.get(category, []))

        if not file_ids:
            return None

        images: list[Image.Image] = []
        for file_id in file_ids:
            image = await self._download_image(bot=bot, file_id=file_id)
            if image is not None:
                images.append(image)

        if not images:
            return None

        composed = self._compose_vertical(images)
        buffer = BytesIO()
        composed.save(buffer, format="PNG")
        return buffer.getvalue()

    async def _download_image(self, bot, file_id: str):
        from PIL import Image

        try:
            telegram_file = await bot.get_file(file_id)
            content = BytesIO()
            await bot.download_file(telegram_file.file_path, destination=content)
            content.seek(0)
            image = Image.open(content)
            image.load()
            return image.convert("RGB")
        except Exception:
            return None

    @staticmethod
    def _compose_vertical(images):
        from PIL import Image

        target_width = 1400
        spacing = 36
        margin = 40
        panel_padding = 20
        inner_width = target_width - margin * 2 - panel_padding * 2

        panels: list[Image.Image] = []
        for source in images:
            scale = inner_width / source.width
            resized_height = max(1, int(source.height * scale))
            resized = source.resize((inner_width, resized_height), Image.Resampling.LANCZOS)

            panel = Image.new(
                "RGB",
                (target_width - margin * 2, resized_height + panel_padding * 2),
                color=(255, 255, 255),
            )
            panel.paste(resized, (panel_padding, panel_padding))
            panels.append(panel)

        total_height = margin * 2 + sum(panel.height for panel in panels) + spacing * (len(panels) - 1)
        canvas = Image.new("RGB", (target_width, total_height), color=(245, 245, 245))

        y = margin
        for panel in panels:
            canvas.paste(panel, (margin, y))
            y += panel.height + spacing

        return canvas
