"""English → Russian translation for clothing item names and colors."""

from __future__ import annotations

EN_TO_RU: dict[str, str] = {
    # tops
    "t-shirt": "футболка", "tee": "футболка", "shirt": "рубашка",
    "blouse": "блузка", "polo": "поло", "tank top": "майка",
    "sweater": "свитер", "pullover": "пуловер", "hoodie": "худи",
    "sweatshirt": "свитшот", "cardigan": "кардиган",
    "turtleneck": "водолазка", "crop top": "кроп-топ", "top": "топ",
    "vest": "жилет", "tunic": "туника", "henley": "хенли",
    "longsleeve": "лонгслив", "long sleeve": "лонгслив",
    "knit short sleeve": "вязаная футболка", "knit": "вязаный",
    "short sleeve": "футболка",
    "tracksuit": "спортивный костюм", "track jacket": "олимпийка",
    # bottoms
    "jeans": "джинсы", "pants": "брюки", "trousers": "брюки",
    "shorts": "шорты", "skirt": "юбка", "leggings": "леггинсы",
    "joggers": "джоггеры", "chinos": "чиносы", "culottes": "кюлоты",
    "cargo pants": "карго-брюки", "cargo": "карго",
    "wide-leg pants": "широкие брюки", "wide-leg": "широкие",
    "slim pants": "зауженные брюки", "slim": "зауженные",
    "straight pants": "прямые брюки", "straight": "прямые",
    "flared pants": "расклешённые брюки", "flared": "расклешённые",
    "midi skirt": "юбка миди", "mini skirt": "мини-юбка",
    "maxi skirt": "юбка макси", "maxi": "макси",
    "sweatpants": "спортивные штаны",
    # outerwear
    "jacket": "куртка", "coat": "пальто", "blazer": "блейзер",
    "parka": "парка", "bomber": "бомбер", "bomber jacket": "бомбер",
    "denim jacket": "джинсовка", "leather jacket": "кожаная куртка",
    "down jacket": "пуховик", "puffer": "пуховик", "puffer jacket": "пуховик",
    "trench": "тренч", "trench coat": "тренч", "windbreaker": "ветровка",
    "raincoat": "дождевик", "fur coat": "шуба", "overcoat": "пальто",
    "shearling": "дублёнка",
    # onepiece / dresses
    "dress": "платье", "jumpsuit": "комбинезон", "romper": "ромпер",
    "overall": "комбинезон", "overalls": "комбинезон",
    "sundress": "сарафан", "gown": "платье",
    # shoes
    "sneakers": "кроссовки", "boots": "ботинки", "ankle boots": "ботильоны",
    "high boots": "высокие сапоги", "knee boots": "сапоги",
    "sandals": "сандалии", "loafers": "лоферы", "heels": "туфли на каблуке",
    "flats": "балетки", "mules": "мюли", "slides": "шлёпанцы",
    "slippers": "тапочки", "oxfords": "оксфорды", "derby": "дерби",
    "pumps": "туфли-лодочки", "chelsea boots": "челси",
    "running shoes": "беговые кроссовки", "trainers": "кроссовки",
    "flip flops": "вьетнамки", "espadrilles": "эспадрильи",
    "ugg boots": "угги", "uggs": "угги",
    # accessories
    "bag": "сумка", "handbag": "сумка", "backpack": "рюкзак",
    "clutch": "клатч", "belt": "ремень", "scarf": "шарф",
    "hat": "шапка", "cap": "кепка", "beanie": "шапка",
    "gloves": "перчатки", "sunglasses": "солнцезащитные очки",
    "watch": "часы", "bracelet": "браслет", "necklace": "колье",
    "earrings": "серьги", "ring": "кольцо", "tie": "галстук",
    "bow tie": "бабочка", "pocket square": "платок",
    "tote": "тоут", "crossbody": "кроссбоди",
}

COLOR_EN_TO_RU: dict[str, str] = {
    "white": "белый", "black": "чёрный", "red": "красный",
    "blue": "синий", "navy": "тёмно-синий", "green": "зелёный",
    "yellow": "жёлтый", "orange": "оранжевый", "pink": "розовый",
    "purple": "фиолетовый", "gray": "серый", "grey": "серый",
    "brown": "коричневый", "beige": "бежевый", "cream": "кремовый",
    "burgundy": "бордовый", "olive": "оливковый", "khaki": "хаки",
    "coral": "коралловый", "turquoise": "бирюзовый",
    "teal": "бирюзово-зелёный",
    "lavender": "лавандовый", "maroon": "тёмно-бордовый",
    "tan": "песочный",
    "ivory": "слоновая кость", "gold": "золотой", "silver": "серебряный",
    "light blue": "голубой", "dark blue": "тёмно-синий",
    "dark green": "тёмно-зелёный", "light green": "светло-зелёный",
    "magenta": "пурпурный", "mustard": "горчичный", "mint": "мятный",
    "salmon": "лососевый", "plum": "сливовый", "charcoal": "графитовый",
    "peach": "персиковый", "lilac": "сиреневый",
}


def is_ascii_name(text: str) -> bool:
    """Check if text is purely ASCII (English name)."""
    return all(ord(c) < 128 for c in text.replace(" ", "").replace("-", ""))


def is_cyrillic(text: str) -> bool:
    """Check if the text contains at least one Cyrillic character."""
    return any("\u0400" <= ch <= "\u04ff" for ch in text)


def translate_display_name(
    raw_name: str | None,
    primary_color: str | None = None,
    item_type: str | None = None,
) -> str | None:
    """Translate display_name to Russian if it came back in English."""
    if raw_name and is_cyrillic(raw_name):
        return raw_name

    # Build Russian name from color + type
    type_str = (item_type or "").strip().lower()
    color_str = (primary_color or "").strip().lower()

    ru_type = EN_TO_RU.get(type_str)
    ru_color = COLOR_EN_TO_RU.get(color_str)

    if not ru_type:
        # Try raw_name as type fallback
        if raw_name:
            name_lower = raw_name.strip().lower()
            ru_type = EN_TO_RU.get(name_lower)

    if ru_type and ru_color:
        return f"{ru_color.capitalize()} {ru_type}"
    if ru_type:
        return ru_type.capitalize()

    # If we got a raw_name that isn't translatable, return as-is
    if raw_name and raw_name.strip():
        return raw_name.strip()
    return None
