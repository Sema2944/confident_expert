from dataclasses import dataclass


@dataclass
class ItemAnalysis:
    type: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    pattern: str | None = None
    season: str | None = None
    formality: str | None = None
    gender_hint: str | None = None


class AIAnalyzeService:
    async def analyze(self, image_bytes: bytes) -> ItemAnalysis:
        # TODO: интеграция с моделью анализа изображения
        return ItemAnalysis(
            type="unknown",
            primary_color="unknown",
            secondary_color="unknown",
            pattern="unknown",
            season="unknown",
            formality="unknown",
            gender_hint="unknown",
        )


_CATEGORY_RU = {
    "top": "верх",
    "bottom": "низ",
    "outerwear": "верхняя одежда",
    "shoes": "обувь",
    "accessory": "аксессуар",
    "onepiece": "цельный образ",
}

_PATTERN_RU = {
    "solid": "однотонная",
    "stripe": "в полоску",
    "check": "в клетку",
    "print": "с принтом",
    "unknown": "не определён",
}

_SEASON_RU = {
    "winter": "зима",
    "demi": "демисезон",
    "summer": "лето",
    "all": "все сезоны",
    "unknown": "не определён",
}

_FORMALITY_RU = {
    "sport": "спортивный",
    "casual": "повседневный",
    "smart": "smart casual",
    "office": "офисный",
    "unknown": "не определён",
}

_GENDER_HINT_RU = {
    "female": "женский",
    "male": "мужской",
    "unisex": "унисекс",
    "unknown": "не определён",
}


def build_russian_item_summary(category: str, analysis: ItemAnalysis) -> str:
    category_ru = _CATEGORY_RU.get(category, category)
    item_type = analysis.type if analysis.type and analysis.type != "unknown" else "тип не определён"
    primary_color = (
        analysis.primary_color
        if analysis.primary_color and analysis.primary_color != "unknown"
        else "не определён"
    )
    secondary_color = (
        analysis.secondary_color
        if analysis.secondary_color and analysis.secondary_color != "unknown"
        else "не определён"
    )
    pattern = _PATTERN_RU.get(analysis.pattern or "unknown", "не определён")
    season = _SEASON_RU.get(analysis.season or "unknown", "не определён")
    formality = _FORMALITY_RU.get(analysis.formality or "unknown", "не определён")
    gender_hint = _GENDER_HINT_RU.get(analysis.gender_hint or "unknown", "не определён")

    return (
        "Вещь добавлена в гардероб.\n"
        f"Категория: {category_ru}.\n"
        f"Тип: {item_type}.\n"
        f"Основной цвет: {primary_color}.\n"
        f"Дополнительный цвет: {secondary_color}.\n"
        f"Узор: {pattern}.\n"
        f"Сезон: {season}.\n"
        f"Стиль: {formality}.\n"
        f"Гендерная рекомендация: {gender_hint}."
    )
