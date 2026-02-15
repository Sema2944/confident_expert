from collections import defaultdict


_WARDROBE_ITEMS: dict[int, list[dict[str, str]]] = defaultdict(list)


def add_item(
    user_id: int,
    category: str,
    telegram_file_id: str,
    item_type: str | None = None,
    primary_color: str | None = None,
    secondary_color: str | None = None,
    pattern: str | None = None,
    season: str | None = None,
    formality: str | None = None,
    gender_hint: str | None = None,
) -> None:
    _WARDROBE_ITEMS[user_id].append(
        {
            "category": category,
            "telegram_file_id": telegram_file_id,
            "type": item_type or "unknown",
            "primary_color": primary_color or "unknown",
            "secondary_color": secondary_color or "unknown",
            "pattern": pattern or "unknown",
            "season": season or "unknown",
            "formality": formality or "unknown",
            "gender_hint": gender_hint or "unknown",
        }
    )


def get_items(user_id: int) -> list[dict[str, str]]:
    return list(_WARDROBE_ITEMS.get(user_id, []))


def delete_item(user_id: int, item_index: int) -> dict[str, str] | None:
    user_items = _WARDROBE_ITEMS.get(user_id)
    if not user_items:
        return None
    if item_index < 0 or item_index >= len(user_items):
        return None
    return user_items.pop(item_index)


def get_category_counts(user_id: int) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for item in _WARDROBE_ITEMS.get(user_id, []):
        counts[item["category"]] += 1
    return dict(counts)
