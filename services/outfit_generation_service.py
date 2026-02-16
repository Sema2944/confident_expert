from dataclasses import dataclass
from pathlib import Path
import random


@dataclass
class OutfitResult:
    description: str
    items: dict
    image_prompt: str


class OutfitService:
    _IMAGE_PROMPT_TEMPLATE = Path(__file__).resolve().parents[1] / "prompts" / "image_generation.txt"
    _CATEGORY_ALIASES: dict[str, str] = {
        "top": "top",
        "tops": "top",
        "верх": "top",
        "bottom": "bottom",
        "bottoms": "bottom",
        "низ": "bottom",
        "onepiece": "onepiece",
        "dress": "onepiece",
        "dresses": "onepiece",
        "цельный образ": "onepiece",
        "платье": "onepiece",
        "outerwear": "outerwear",
        "верхняя одежда": "outerwear",
        "shoe": "shoes",
        "shoes": "shoes",
        "обувь": "shoes",
        "accessory": "accessory",
        "accessories": "accessory",
        "аксессуар": "accessory",
        "аксессуары": "accessory",
    }

    @classmethod
    def _normalize_category(cls, category: str | None) -> str | None:
        if not category:
            return None
        cleaned = category.strip().lower()
        return cls._CATEGORY_ALIASES.get(cleaned, cleaned)

    @staticmethod
    def _preferred_file_id(item: dict | None) -> str | None:
        if not item:
            return None
        processed = item.get("processed_file_id")
        if isinstance(processed, str) and processed.strip():
            return processed
        original = item.get("telegram_file_id")
        if isinstance(original, str) and original.strip():
            return original
        return None

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
            category = self._normalize_category(item.get("category"))
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
        start_offset = random.randint(0, 1_000_000)
        for index in range(count):
            item_offset = start_offset + index
            use_dress = bool(dresses and (not tops or not bottoms or item_offset % 2 == 1))

            top = None if use_dress else self._pick_with_offset(tops, item_offset)
            bottom = None if use_dress else self._pick_with_offset(bottoms, item_offset)
            dress = self._pick_with_offset(dresses, item_offset) if use_dress else None

            if use_dress and not dress:
                continue
            if not use_dress and (not top or not bottom):
                continue

            shoe = self._pick_with_offset(shoes, item_offset)
            outerwear = self._pick_with_offset(outerwears, item_offset) if outerwears else None
            accessory = self._pick_with_offset(accessories, item_offset) if accessories else None

            top_file_id = self._preferred_file_id(top)
            bottom_file_id = self._preferred_file_id(bottom)
            dress_file_id = self._preferred_file_id(dress)
            outerwear_file_id = self._preferred_file_id(outerwear)
            shoe_file_id = self._preferred_file_id(shoe)
            accessory_file_id = self._preferred_file_id(accessory)

            items_payload = {
                "top": [top_file_id] if top_file_id else [],
                "bottom": [bottom_file_id] if bottom_file_id else [],
                "dress": [dress_file_id] if dress_file_id else [],
                "outerwear": [outerwear_file_id] if outerwear_file_id else [],
                "shoes": [shoe_file_id] if shoe_file_id else [],
                "accessories": [accessory_file_id] if accessory_file_id else [],
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
