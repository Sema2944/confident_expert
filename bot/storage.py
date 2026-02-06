from collections import defaultdict


_WARDROBE_ITEMS: dict[int, list[dict[str, str]]] = defaultdict(list)


def add_item(user_id: int, category: str, telegram_file_id: str) -> None:
    _WARDROBE_ITEMS[user_id].append(
        {"category": category, "telegram_file_id": telegram_file_id}
    )


def get_items(user_id: int) -> list[dict[str, str]]:
    return list(_WARDROBE_ITEMS.get(user_id, []))


def get_category_counts(user_id: int) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for item in _WARDROBE_ITEMS.get(user_id, []):
        counts[item["category"]] += 1
    return dict(counts)
