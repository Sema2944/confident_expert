from dataclasses import dataclass
import base64
import json
import logging

import httpx

from config.categories import CATEGORY_LABELS_RU
from config.settings import settings
from bot.utils.translate import (
    EN_TO_RU, COLOR_EN_TO_RU, is_cyrillic, translate_display_name,
)


@dataclass
class ItemAnalysis:
    type: str | None = None
    display_name: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    pattern: str | None = None
    season: str | None = None
    formality: str | None = None
    gender_hint: str | None = None
    photo_quality: str | None = None


class AIAnalyzeService:
    _PATTERN_VALUES = {"solid", "stripe", "check", "print", "unknown"}
    _SEASON_VALUES = {"winter", "demi", "summer", "all", "unknown"}
    _FORMALITY_VALUES = {"sport", "casual", "smart", "office", "unknown"}
    _GENDER_VALUES = {"female", "male", "unisex", "unknown"}
    _PHOTO_QUALITY_VALUES = {"good", "poor", "unclear"}

    async def analyze(self, image_bytes: bytes) -> ItemAnalysis:
        if not settings.ai_api_key:
            logging.warning("AI_API_KEY is empty; item analysis is disabled.")
            return self._unknown_analysis()

        if not image_bytes:
            logging.warning("Image bytes are empty; cannot analyze item photo.")
            return self._unknown_analysis()

        prompt = self._load_prompt()
        if not prompt:
            return self._unknown_analysis()

        payload = {
            "model": settings.ai_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": self._build_data_url(image_bytes),
                                "detail": "low",
                            },
                        },
                    ],
                }
            ],
        }

        headers = {
            "Authorization": f"Bearer {settings.ai_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{settings.ai_api_base.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except Exception as error:
            logging.exception("Item analysis request failed: %s", error)
            return self._unknown_analysis()

        content = self._extract_content(response.json())
        if not content:
            logging.warning("Item analysis response did not contain message content.")
            return self._unknown_analysis()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logging.warning("Item analysis returned invalid JSON: %s", content)
            return self._unknown_analysis()

        return self._parse_analysis(parsed)

    def _load_prompt(self) -> str | None:
        try:
            with open("prompts/item_analysis.txt", "r", encoding="utf-8") as file:
                return file.read().strip()
        except OSError as error:
            logging.exception("Failed to read item analysis prompt file: %s", error)
            return None

    @staticmethod
    def _build_data_url(image_bytes: bytes) -> str:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    @staticmethod
    def _extract_content(response_data: dict) -> str | None:
        choices = response_data.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message") or {}
        return message.get("content")

    def _parse_analysis(self, payload: dict) -> ItemAnalysis:
        item_type = self._normalize_text(payload.get("type"))
        primary_color = self._normalize_text(payload.get("primary_color"))
        raw_display = payload.get("display_name")
        display_name = translate_display_name(raw_display, primary_color, item_type)

        return ItemAnalysis(
            type=item_type,
            display_name=display_name,
            primary_color=primary_color,
            secondary_color=self._normalize_text(payload.get("secondary_color")),
            pattern=self._normalize_enum(payload.get("pattern"), self._PATTERN_VALUES),
            season=self._normalize_enum(payload.get("season"), self._SEASON_VALUES),
            formality=self._normalize_enum(payload.get("formality"), self._FORMALITY_VALUES),
            gender_hint=self._normalize_enum(payload.get("gender_hint"), self._GENDER_VALUES),
            photo_quality=self._normalize_enum(payload.get("photo_quality"), self._PHOTO_QUALITY_VALUES),
        )

    @staticmethod
    def _normalize_text(value: object) -> str:
        if not isinstance(value, str):
            return "unknown"
        cleaned = value.strip().lower()
        return cleaned or "unknown"

    @staticmethod
    def _normalize_enum(value: object, allowed: set[str]) -> str:
        if not isinstance(value, str):
            return "unknown"
        normalized = value.strip().lower()
        if not normalized:
            return "unknown"
        return normalized if normalized in allowed else "unknown"

    @staticmethod
    def _unknown_analysis() -> ItemAnalysis:
        return ItemAnalysis(
            type="unknown",
            primary_color="unknown",
            secondary_color="unknown",
            pattern="unknown",
            season="unknown",
            formality="unknown",
            gender_hint="unknown",
            photo_quality="good",
        )


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
    has_any = any(
        getattr(analysis, field) not in (None, "unknown")
        for field in ("type", "primary_color", "pattern", "season", "formality")
    )

    if not has_any:
        return (
            "✅ Вещь добавлена в гардероб.\n\n"
            "Не удалось автоматически определить атрибуты. "
            "Это не повлияет на подбор образов, но с атрибутами результат будет точнее."
        )

    category_label = CATEGORY_LABELS_RU.get(category, category)
    display = analysis.display_name
    header = f"✅ Добавлено: {display}" if display else f"✅ Добавлено: {category_label}"
    lines = [f"{header}\n", "📋 Что я вижу:"]

    item_type = analysis.type
    if item_type and item_type != "unknown":
        ru_type = EN_TO_RU.get(item_type.lower(), item_type)
        lines.append(f"• Тип: {ru_type}")

    color = analysis.primary_color
    if color and color != "unknown":
        ru_color = COLOR_EN_TO_RU.get(color.lower(), color)
        lines.append(f"• Цвет: {ru_color}")

    pattern = analysis.pattern
    if pattern and pattern != "unknown":
        lines.append(f"• Принт: {_PATTERN_RU.get(pattern, pattern)}")

    season = analysis.season
    if season and season != "unknown":
        lines.append(f"• Сезон: {_SEASON_RU.get(season, season)}")

    formality = analysis.formality
    if formality and formality != "unknown":
        lines.append(f"• Стиль: {_FORMALITY_RU.get(formality, formality)}")

    return "\n".join(lines)
