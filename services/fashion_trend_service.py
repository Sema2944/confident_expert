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
                "- Vogue: свежий англоязычный материал",
                "- Who What Wear: свежий англоязычный материал",
            ]

        lines.extend(normalized[:5])
        lines.append("Совет: добавляйте 1-2 трендовые детали к базовым вещам, чтобы образ оставался носибельным.")
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
            return f"{source_name}: свежий англоязычный материал"
        return f"{source_name}: {headline}"

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
