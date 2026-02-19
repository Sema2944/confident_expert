"""Единый реестр категорий гардероба."""

CATEGORIES = ("top", "bottom", "outerwear", "shoes", "accessory", "onepiece")

CATEGORY_LABELS_RU: dict[str, str] = {
    "top": "👕 Верх",
    "bottom": "👖 Низ",
    "outerwear": "🧥 Верхняя одежда",
    "shoes": "👟 Обувь",
    "accessory": "🧢 Аксессуары",
    "onepiece": "👔 Цельный образ",
}

CATEGORY_ALIASES: dict[str, str] = {
    # Русские
    "верх": "top",
    "👕 верх": "top",
    "низ": "bottom",
    "👖 низ": "bottom",
    "верхняя одежда": "outerwear",
    "🧥 верхняя одежда": "outerwear",
    "обувь": "shoes",
    "👟 обувь": "shoes",
    "аксессуар": "accessory",
    "аксессуары": "accessory",
    "🧢 аксессуары": "accessory",
    "платье": "onepiece",
    "цельный образ": "onepiece",
    "👔 цельный образ": "onepiece",
    # Английские (из AI-ответов)
    "top": "top",
    "tops": "top",
    "bottom": "bottom",
    "bottoms": "bottom",
    "outerwear": "outerwear",
    "shoes": "shoes",
    "shoe": "shoes",
    "accessory": "accessory",
    "accessories": "accessory",
    "dress": "onepiece",
    "dresses": "onepiece",
    "onepiece": "onepiece",
}


def normalize_category(text: str) -> str | None:
    """Нормализует текст категории к каноническому значению."""
    return CATEGORY_ALIASES.get((text or "").strip().lower())
