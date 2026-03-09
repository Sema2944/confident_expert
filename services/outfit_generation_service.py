from dataclasses import dataclass
import json
import logging
from pathlib import Path
import random

import httpx

from config.categories import normalize_category
from config.settings import settings


@dataclass
class OutfitResult:
    description: str
    items: dict
    image_prompt: str


# --- Фильтрация по occasion ---

_OCCASION_PREFER: dict[str, set[str]] = {
    "work_office": {"office", "smart"},
    "interview": {"office", "smart"},
    "date": {"smart", "casual"},
    "party": {"smart", "casual"},
    "walk": {"casual", "sport"},
    "sport_active": {"sport"},
    "going_out": {"smart", "casual"},
    "sport_travel": {"sport", "casual"},
    "casual": set(),
}

_OCCASION_EXCLUDE: dict[str, set[str]] = {
    "work_office": {"sport"},
    "interview": {"sport", "casual"},
    "date": {"sport"},
    "party": {"sport"},
    "walk": {"office"},
    "sport_active": {"office", "smart"},
    "going_out": {"sport"},
    "sport_travel": {"office"},
    "casual": set(),
}

# --- Фильтрация по season ---

_SEASON_ALLOWED: dict[str, set[str]] = {
    "winter": {"winter", "all", "demi", "unknown"},
    "summer": {"summer", "all", "unknown"},
    "demi": {"demi", "all", "unknown"},
    "all": {"winter", "summer", "demi", "all", "unknown"},
}

# --- Цветовой scoring ---

NEUTRAL_COLORS = {
    "black", "white", "gray", "grey", "navy", "beige", "brown", "cream",
    "чёрный", "белый", "серый", "бежевый", "тёмно-синий", "коричневый",
}


def _color_compatibility_score(items_in_outfit: list[dict]) -> float:
    """Оценка цветовой совместимости. 1.0 = хорошо, 0.0 = плохо."""
    colors = []
    for item in items_in_outfit:
        pc = (item.get("primary_color") or "").strip().lower()
        if pc and pc != "unknown":
            colors.append(pc)

    if len(colors) <= 1:
        return 1.0

    neutral_count = sum(1 for c in colors if c in NEUTRAL_COLORS)

    if neutral_count >= len(colors) - 1:
        return 1.0

    accent_colors = [c for c in colors if c not in NEUTRAL_COLORS]
    if len(set(accent_colors)) == 1:
        return 0.9

    if len(set(accent_colors)) >= 3:
        return 0.3

    return 0.6


def _filter_items_for_context(
    items: list[dict],
    occasion: str,
    season: str,
) -> list[dict]:
    """Фильтрует вещи по контексту (повод + сезон).
    Если после фильтрации слишком мало вещей — ослабляет фильтры."""
    allowed_seasons = _SEASON_ALLOWED.get(season, _SEASON_ALLOWED["all"])
    exclude_formality = _OCCASION_EXCLUDE.get(occasion, set())

    filtered = []
    for item in items:
        item_season = (item.get("season") or "unknown").strip().lower()
        item_formality = (item.get("formality") or "unknown").strip().lower()

        if item_season not in allowed_seasons:
            continue

        if item_formality in exclude_formality:
            continue

        filtered.append(item)

    # Стратегия ослабления: проверяем, есть ли обязательные категории
    required_cats = {"top", "shoes"}
    filtered_cats = {normalize_category(i.get("category")) for i in filtered}

    for cat in required_cats:
        if cat not in filtered_cats:
            # Добавляем вещи этой категории без фильтра
            for item in items:
                if normalize_category(item.get("category")) == cat and item not in filtered:
                    filtered.append(item)

    # Если нет ни bottom ни onepiece — ослабить
    if "bottom" not in filtered_cats and "onepiece" not in filtered_cats:
        for item in items:
            cat = normalize_category(item.get("category"))
            if cat in ("bottom", "onepiece") and item not in filtered:
                filtered.append(item)

    # Зима: верхняя одежда обязательна — добавляем даже если сезон не совпадает
    if season == "winter":
        filtered_cats = {normalize_category(i.get("category")) for i in filtered}
        if "outerwear" not in filtered_cats:
            for item in items:
                if normalize_category(item.get("category")) == "outerwear" and item not in filtered:
                    filtered.append(item)

    return filtered


def _apply_liked_boost(grouped: dict[str, list[dict]], liked_file_ids: set[str]) -> None:
    """Перемещает лайкнутые вещи в начало списка каждой категории."""
    if not liked_file_ids:
        return
    for category, items_list in grouped.items():
        liked = [i for i in items_list if i.get("telegram_file_id") in liked_file_ids
                 or i.get("processed_file_id") in liked_file_ids]
        others = [i for i in items_list if i not in liked]
        grouped[category] = liked + others


def _apply_recent_penalty(grouped: dict[str, list[dict]], recently_used: set[str]) -> None:
    """Перемещает недавно использованные вещи в конец списка каждой категории."""
    if not recently_used:
        return
    for category, items_list in grouped.items():
        recent = [i for i in items_list if i.get("telegram_file_id") in recently_used
                  or i.get("processed_file_id") in recently_used]
        others = [i for i in items_list if i not in recent]
        grouped[category] = others + recent


class OutfitService:
    _IMAGE_PROMPT_TEMPLATE = Path(__file__).resolve().parents[1] / "prompts" / "image_generation.txt"

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

    _OUTFIT_PROMPT_TEMPLATE = Path(__file__).resolve().parents[1] / "prompts" / "outfit_generation.txt"

    async def _generate_outfits_with_ai(
        self,
        items: list[dict],
        occasion: str,
        season: str,
        count: int,
    ) -> list[OutfitResult]:
        """Генерация образов через AI API."""
        # Строим JSON-массив вещей для промпта
        items_for_prompt = []
        items_by_id: dict[int, dict] = {}
        for item in items:
            item_id = item.get("id")
            items_by_id[item_id] = item
            items_for_prompt.append({
                "item_id": item_id,
                "category": item.get("category"),
                "type": item.get("type"),
                "primary_color": item.get("primary_color"),
                "pattern": item.get("pattern"),
                "season": item.get("season"),
                "formality": item.get("formality"),
            })

        template = self._OUTFIT_PROMPT_TEMPLATE.read_text(encoding="utf-8")
        prompt = template.format(
            occasion=occasion,
            season=season,
            n=count,
            items_list=json.dumps(items_for_prompt, ensure_ascii=False),
        )

        headers = {
            "Authorization": f"Bearer {settings.ai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.ai_model,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.ai_api_base.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        content = (response.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
        parsed = json.loads(content)
        outfits_data = parsed.get("outfits", [])

        results: list[OutfitResult] = []
        for outfit_data in outfits_data:
            raw_items = outfit_data.get("items", {})
            # Преобразуем item_id в file_id
            items_payload: dict[str, list[str]] = {}
            for cat_key, id_list in raw_items.items():
                file_ids = []
                for raw_id in (id_list or []):
                    item = items_by_id.get(int(raw_id))
                    fid = self._preferred_file_id(item) if item else None
                    if fid:
                        file_ids.append(fid)
                items_payload[cat_key] = file_ids

            description = outfit_data.get("description_ru", "")
            results.append(OutfitResult(
                description=description,
                items=items_payload,
                image_prompt="",
            ))

        return results

    def _build_one_outfit(
        self,
        grouped: dict[str, list[dict]],
        item_offset: int,
        occasion: str,
        season: str,
        index: int,
    ) -> tuple[OutfitResult | None, list[dict]]:
        """Строит один вариант образа. Возвращает (result, items_used)."""
        tops = grouped.get("top", [])
        bottoms = grouped.get("bottom", [])
        dresses = grouped.get("onepiece", [])
        outerwears = grouped.get("outerwear", [])
        shoes = grouped.get("shoes", [])
        accessories = grouped.get("accessory", [])

        if not shoes:
            return None, []

        use_dress = bool(dresses and (not tops or not bottoms or item_offset % 2 == 1))

        top = None if use_dress else self._pick_with_offset(tops, item_offset)
        bottom = None if use_dress else self._pick_with_offset(bottoms, item_offset)
        dress = self._pick_with_offset(dresses, item_offset) if use_dress else None

        if use_dress and not dress:
            return None, []
        if not use_dress and (not top or not bottom):
            return None, []

        shoe = self._pick_with_offset(shoes, item_offset)
        outerwear = self._pick_with_offset(outerwears, item_offset) if outerwears else None
        accessory = self._pick_with_offset(accessories, item_offset) if accessories else None

        outfit_items = [i for i in [top, bottom, dress, shoe, outerwear, accessory] if i]

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
            top=top, bottom=bottom, dress=dress,
            outerwear=outerwear, shoes=shoe, accessory=accessory,
        )

        result = OutfitResult(
            description=description,
            items=items_payload,
            image_prompt=image_prompt,
        )
        return result, outfit_items

    async def _generate_outfits_local(
        self,
        items: list[dict],
        occasion: str,
        season: str,
        count: int,
        liked_file_ids: set[str] | None = None,
        recently_used: set[str] | None = None,
        exclude_file_ids: set[str] | None = None,
    ) -> list[OutfitResult]:
        """Локальная генерация образов (без AI)."""
        filtered = _filter_items_for_context(items, occasion, season)

        grouped: dict[str, list[dict]] = {}
        for item in filtered:
            category = normalize_category(item.get("category"))
            if not category:
                continue
            grouped.setdefault(category, []).append(item)

        if liked_file_ids:
            _apply_liked_boost(grouped, liked_file_ids)
        if recently_used:
            _apply_recent_penalty(grouped, recently_used)

        if not grouped.get("shoes"):
            return []

        results: list[OutfitResult] = []
        start_offset = random.randint(0, 1_000_000)

        for index in range(count):
            candidates: list[tuple[float, OutfitResult]] = []

            for attempt in range(10):
                item_offset = start_offset + index * 10 + attempt
                result, outfit_items = self._build_one_outfit(
                    grouped, item_offset, occasion, season, index,
                )
                if result is None:
                    continue

                score = _color_compatibility_score(outfit_items)
                # Winter bonus: prioritize outfits with outerwear
                if season == "winter" and result.items.get("outerwear"):
                    score += 0.5
                # Penalty for excluded items (previous outfit on reroll)
                if exclude_file_ids:
                    outfit_fids: set[str] = set()
                    for fids in result.items.values():
                        outfit_fids.update(fids)
                    overlap = outfit_fids & exclude_file_ids
                    if overlap:
                        score -= len(overlap) * 1.0
                candidates.append((score, result))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                # Among top-5 by score, pick randomly for variety
                top = candidates[:5]
                random.shuffle(top)
                results.append(top[0][1])

        return results

    def _build_one_outfit_with_base(
        self,
        grouped: dict[str, list[dict]],
        base_item: dict,
        base_category: str,
        occasion: str,
        season: str,
        index: int,
        exclude_item_ids: set[int] | None = None,
    ) -> tuple[OutfitResult | None, list[dict]]:
        """Build one outfit around a fixed base item."""
        exclude = exclude_item_ids or set()

        def _pick_best(items_list: list[dict], base_items: list[dict]) -> dict | None:
            available = [i for i in items_list if i.get("id") not in exclude]
            if not available:
                available = items_list  # fallback
            if not available:
                return None
            # Score by color compatibility with base
            scored = []
            for item in available:
                test_outfit = base_items + [item]
                score = _color_compatibility_score(test_outfit) + random.random() * 0.1
                scored.append((score, item))
            scored.sort(key=lambda x: x[0], reverse=True)
            return scored[0][1]

        tops = grouped.get("top", [])
        bottoms = grouped.get("bottom", [])
        dresses = grouped.get("onepiece", [])
        outerwears = grouped.get("outerwear", [])
        shoes = grouped.get("shoes", [])
        accessories = grouped.get("accessory", [])

        # Determine outfit structure based on base category
        top = bottom = dress = shoe = outerwear = accessory = None
        base_items_so_far = [base_item]

        if base_category == "onepiece":
            dress = base_item
        elif base_category == "bottom":
            bottom = base_item
            top = _pick_best(tops, base_items_so_far)
            if top:
                base_items_so_far.append(top)
        elif base_category == "top":
            top = base_item
            bottom = _pick_best(bottoms, base_items_so_far)
            if bottom:
                base_items_so_far.append(bottom)
        elif base_category == "outerwear":
            outerwear = base_item
            # Need top+bottom or dress
            if dresses:
                dress = _pick_best(dresses, base_items_so_far)
                if dress:
                    base_items_so_far.append(dress)
            if not dress:
                top = _pick_best(tops, base_items_so_far)
                if top:
                    base_items_so_far.append(top)
                bottom = _pick_best(bottoms, base_items_so_far)
                if bottom:
                    base_items_so_far.append(bottom)
        elif base_category == "shoes":
            shoe = base_item
            # Need top+bottom or dress
            if dresses and random.random() > 0.5:
                dress = _pick_best(dresses, base_items_so_far)
                if dress:
                    base_items_so_far.append(dress)
            if not dress:
                top = _pick_best(tops, base_items_so_far)
                if top:
                    base_items_so_far.append(top)
                bottom = _pick_best(bottoms, base_items_so_far)
                if bottom:
                    base_items_so_far.append(bottom)

        # Fill missing required slots
        if not shoe and base_category != "shoes":
            shoe = _pick_best(shoes, base_items_so_far)
            if shoe:
                base_items_so_far.append(shoe)
        if not shoe:
            return None, []

        if not dress and not top and base_category not in ("top", "onepiece"):
            top = _pick_best(tops, base_items_so_far)
            if top:
                base_items_so_far.append(top)
        if not dress and not bottom and base_category not in ("bottom", "onepiece"):
            bottom = _pick_best(bottoms, base_items_so_far)
            if bottom:
                base_items_so_far.append(bottom)

        if not dress and not (top and bottom):
            # Try dress as fallback
            dress = _pick_best(dresses, base_items_so_far)
            if dress:
                base_items_so_far.append(dress)
            if not dress:
                return None, []

        # Optional outerwear for winter
        if not outerwear and season == "winter" and outerwears and base_category != "outerwear":
            outerwear = _pick_best(outerwears, base_items_so_far)
            if outerwear:
                base_items_so_far.append(outerwear)

        # Optional accessory
        if accessories and base_category != "accessory":
            accessory = _pick_best(accessories, base_items_so_far)

        outfit_items = [i for i in [top, bottom, dress, shoe, outerwear, accessory] if i]
        items_payload = {
            "top": [self._preferred_file_id(top)] if self._preferred_file_id(top) else [],
            "bottom": [self._preferred_file_id(bottom)] if self._preferred_file_id(bottom) else [],
            "dress": [self._preferred_file_id(dress)] if self._preferred_file_id(dress) else [],
            "outerwear": [self._preferred_file_id(outerwear)] if self._preferred_file_id(outerwear) else [],
            "shoes": [self._preferred_file_id(shoe)] if self._preferred_file_id(shoe) else [],
            "accessories": [self._preferred_file_id(accessory)] if self._preferred_file_id(accessory) else [],
        }

        use_dress = dress is not None
        description = (
            f"Образ #{index + 1}: {occasion}, {season}. "
            f"{'Платье + обувь' if use_dress else 'Верх + низ + обувь'}"
            f"{' + верхняя одежда' if outerwear else ''}"
            f"{' + аксессуары' if accessory else ''}."
        )
        image_prompt = self._build_image_prompt(
            top=top, bottom=bottom, dress=dress,
            outerwear=outerwear, shoes=shoe, accessory=accessory,
        )
        return OutfitResult(description=description, items=items_payload, image_prompt=image_prompt), outfit_items

    async def generate_outfits_around_base(
        self,
        items: list[dict],
        base_item_id: int,
        occasion: str,
        season: str,
        count: int = 3,
        user_id: int | None = None,
    ) -> list[OutfitResult]:
        """Generate count outfits where base_item is always included."""
        filtered = _filter_items_for_context(items, occasion, season)

        # Find base item
        base_item = next((i for i in items if i.get("id") == base_item_id), None)
        if not base_item:
            return []
        base_category = normalize_category(base_item.get("category"))
        if not base_category:
            return []

        # Ensure base item is in filtered list
        if base_item not in filtered:
            filtered.append(base_item)

        grouped: dict[str, list[dict]] = {}
        for item in filtered:
            category = normalize_category(item.get("category"))
            if not category:
                continue
            grouped.setdefault(category, []).append(item)

        results: list[OutfitResult] = []
        used_item_ids: set[int] = set()

        for index in range(count):
            # Exclude non-base items from previous outfits
            exclude = used_item_ids - {base_item_id}

            result, outfit_items = self._build_one_outfit_with_base(
                grouped, base_item, base_category, occasion, season, index,
                exclude_item_ids=exclude,
            )
            if result is None:
                continue

            # Track used items
            for item in outfit_items:
                iid = item.get("id")
                if iid:
                    used_item_ids.add(iid)

            results.append(result)

        return results

    @staticmethod
    def pick_base_item(items: list[dict], season: str = "all") -> dict | None:
        """Auto-pick the best base item by priority."""
        by_cat: dict[str, list[dict]] = {}
        for item in items:
            cat = normalize_category(item.get("category"))
            if cat:
                by_cat.setdefault(cat, []).append(item)

        # Priority: onepiece > bottom > top > outerwear (winter)
        if "onepiece" in by_cat:
            return random.choice(by_cat["onepiece"])
        if "bottom" in by_cat:
            return random.choice(by_cat["bottom"])
        if "top" in by_cat:
            return random.choice(by_cat["top"])
        if season == "winter" and "outerwear" in by_cat:
            return random.choice(by_cat["outerwear"])
        return None

    async def generate_outfits(
        self,
        items: list[dict],
        occasion: str,
        season: str,
        count: int,
        user_id: int | None = None,
        exclude_file_ids: set[str] | None = None,
    ) -> list[OutfitResult]:
        # Получаем лайкнутые вещи для бустинга
        liked_file_ids: set[str] = set()
        if user_id:
            try:
                from bot.storage import get_liked_items
                liked_file_ids = set(await get_liked_items(user_id))
            except Exception:
                pass

        # Штраф за недавно использованные вещи
        recently_used: set[str] = set()
        if user_id:
            try:
                from bot.storage import get_recent_outfit_item_ids
                recently_used = await get_recent_outfit_item_ids(user_id, days=3)
            except Exception:
                pass

        if settings.ai_api_key:
            try:
                filtered = _filter_items_for_context(items, occasion, season)
                return await self._generate_outfits_with_ai(filtered, occasion, season, count)
            except Exception:
                logging.exception("AI outfit generation failed, using local fallback")

        return await self._generate_outfits_local(
            items, occasion, season, count,
            liked_file_ids=liked_file_ids,
            recently_used=recently_used,
            exclude_file_ids=exclude_file_ids,
        )
