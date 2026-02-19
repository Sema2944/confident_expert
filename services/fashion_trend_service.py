from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re


@dataclass(frozen=True)
class TrendSignal:
    source_url: str
    headline: str


class FashionTrendService:
    """Builds a short Russian digest for current fashion trends."""

    async def get_trend_digest(self, season: str = "all", year: int | None = None) -> str:
        target_year = year or datetime.now().year
        demo_signals = [
            "https://www.vogue.com/feed/rss :: New York shows focused on wearable layering and quiet luxury",
            "https://www.whowhatwear.com/rss :: Street style highlights deep chocolate, burgundy and gray",
            "https://www.harpersbazaar.com/rss/all.xml :: Модные дома возвращают акцентные аксессуары",
        ]
        return self._fallback_trends(season=season, year=target_year, source_signals=demo_signals)

    @classmethod
    def _fallback_trends(cls, season: str, year: int, source_signals: list[str]) -> str:
        season_label = season if season and season != "all" else "текущий сезон"
        lines = [f"Тренды {season_label} {year}:"]

        normalized: list[str] = []
        for signal in source_signals:
            localized = cls._localize_signal_for_russian(signal)
            if localized:
                normalized.append(f"- {localized}")

        if not normalized:
            normalized = [
                "- Vogue: носибельная многослойность и тихая роскошь в базе гардероба.",
                "- Who What Wear: шоколадные и бордовые оттенки + серый как нейтральная база.",
            ]

        lines.extend(normalized[:5])
        lines.append(f"Где следить за трендами на русском: {cls._russian_style_sources_for_digest(source_signals)}")
        lines.append("Совет: берите один заметный акцент (цвет, аксессуар или фактуру) и сочетайте с базовыми вещами.")
        return "\n".join(lines)

    @classmethod
    def _localize_signal_for_russian(cls, signal: str) -> str:
        if "::" not in signal:
            return ""

        source_url, headline = [part.strip() for part in signal.split("::", maxsplit=1)]
        if not headline:
            return ""

        source_name = cls._source_name(source_url)
        if cls._looks_english(headline):
            insight = cls._english_headline_hint(source_name)
            return f"{source_name}: {insight}"

        clarified = cls._clarify_headline(headline)
        return f"{source_name}: {clarified}"

    @staticmethod
    def _english_headline_hint(source_name: str) -> str:
        hints = {
            "Vogue": "акцент на носибельную многослойность и качественную базу",
            "Who What Wear": "ставка на трендовые оттенки (шоколад, бордо, серый) и понятные стилизации",
            "Harper's Bazaar": "выразительные аксессуары снова становятся центром образа",
        }
        return hints.get(source_name, "свежий англоязычный разбор сезонных трендов")

    @staticmethod
    def _clarify_headline(headline: str) -> str:
        lowered = headline.lower()
        if "акцент" in lowered and "аксессуар" in lowered:
            return (
                "модные дома возвращают акцентные аксессуары: крупные серьги, широкие ремни и заметные сумки "
                "— они собирают образ и делают базу визуально дороже"
            )
        return headline

    @classmethod
    def _russian_style_sources_for_digest(cls, source_signals: list[str]) -> str:
        known_sources: list[str] = []
        for signal in source_signals:
            source_url = signal.split("::", maxsplit=1)[0].strip()
            known_sources.append(cls._source_name(source_url))

        references: list[str] = []
        for source_name in known_sources:
            references.extend(cls._russian_style_sources(source_name))

        if not references:
            references = cls._russian_style_sources("Fashion source")

        deduplicated: list[str] = []
        seen: set[str] = set()
        for item in references:
            if item not in seen:
                seen.add(item)
                deduplicated.append(item)

        return "; ".join(deduplicated)

    @staticmethod
    def _russian_style_sources(source_name: str) -> list[str]:
        source_map = {
            "Vogue": [
                "Vogue Россия — https://www.vogue.ru/fashion/trends",
                "The Blueprint — https://theblueprint.ru/fashion",
            ],
            "Who What Wear": [
                "BURO. — https://www.buro247.ru/fashion",
                "GRAZIA Россия — https://graziamagazine.ru/fashion",
            ],
            "Harper's Bazaar": [
                "Harper's Bazaar Kazakhstan (рус.) — https://harpersbazaar.kz/category/fashion",
                "The Blueprint — https://theblueprint.ru/fashion",
            ],
        }
        return source_map.get(source_name, ["The Blueprint — https://theblueprint.ru/fashion"])

    @staticmethod
    def _source_name(source_url: str) -> str:
        lowered = source_url.lower()
        if "vogue" in lowered:
            return "Vogue"
        if "whowhatwear" in lowered:
            return "Who What Wear"
        if "harpersbazaar" in lowered:
            return "Harper's Bazaar"
        return "Fashion source"

    @staticmethod
    def _looks_english(text: str) -> bool:
        return re.search(r"[A-Za-z]", text) is not None and re.search(r"[А-Яа-яЁё]", text) is None
