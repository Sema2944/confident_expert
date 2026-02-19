"""Анализ гардероба: пробелы, дисбаланс, рекомендации."""

from config.categories import CATEGORY_LABELS_RU

_SEASON_RU = {
    "winter": "зима", "demi": "демисезон", "summer": "лето", "all": "все сезоны",
}
_FORMALITY_RU = {
    "sport": "спортивный", "casual": "повседневный", "smart": "smart casual", "office": "офисный",
}


def analyze_wardrobe_gaps(items: list[dict]) -> str | None:
    """Возвращает текст с подсказками или None, если подсказок нет."""
    if not items:
        return None

    categories = {item.get("category") for item in items}
    hints: list[str] = []

    # Приоритет 1: нет обуви
    if "shoes" not in categories:
        hints.append("👟 Добавь обувь — без неё я не могу собрать полный образ.")

    # Приоритет 2: нет верха/низа
    if "onepiece" not in categories:
        if "top" not in categories:
            hints.append("👕 Добавь хотя бы одну вещь верха или платье, чтобы я мог собирать образы.")
        if "bottom" not in categories:
            hints.append("👖 Добавь брюки или юбку — пока не из чего собрать низ образа.")

    # Приоритет 3: мало вещей
    if len(items) < 3:
        hints.append("📦 Пока в гардеробе мало вещей. Добавь хотя бы 3 — и я покажу первый образ.")

    # Приоритет 4: дисбаланс по сезону
    if not hints:
        seasons = {
            item.get("season")
            for item in items
            if item.get("season") and item.get("season") != "unknown"
        }
        if len(seasons) == 1:
            season = next(iter(seasons))
            label = _SEASON_RU.get(season, season)
            if season != "all":
                hints.append(f"🌦 Все вещи на один сезон ({label}). Добавь вещи на другие сезоны для разнообразия.")

    # Приоритет 5: дисбаланс по стилю
    if not hints:
        formalities = {
            item.get("formality")
            for item in items
            if item.get("formality") and item.get("formality") != "unknown"
        }
        if len(formalities) == 1:
            formality = next(iter(formalities))
            label = _FORMALITY_RU.get(formality, formality)
            hints.append(f"💼 Все вещи {label}-стиля. Для разных поводов добавь вещи другого стиля.")

    # Приоритет 6: нет аксессуаров при > 10 вещах
    if not hints and len(items) > 10 and "accessory" not in categories:
        hints.append("🧢 Попробуй добавить аксессуар — он может сделать образы выразительнее.")

    if not hints:
        return None

    return "\n".join(hints[:2])
