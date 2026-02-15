from __future__ import annotations

from datetime import datetime
import os
from urllib.parse import urlparse
import xml.etree.ElementTree as ET


class FashionTrendService:
    _DEFAULT_FEEDS = (
        "https://www.vogue.com/feed/rss",
        "https://www.whowhatwear.com/rss",
    )

    _SOURCE_BY_HOST = {
        "vogue.com": "Vogue",
        "www.vogue.com": "Vogue",
        "whowhatwear.com": "Who What Wear",
        "www.whowhatwear.com": "Who What Wear",
    }

    async def get_trend_digest(self) -> str:
        now = datetime.now()
        season = self._season_for_month(now.month)
        source_signals = await self._collect_source_signals()
        return self._fallback_trends(season=season, year=now.year, source_signals=source_signals)

    async def _collect_source_signals(self) -> list[str]:
        collected: list[str] = []
        try:
            import httpx
        except ImportError:
            return collected

        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            for feed_url in self._feed_urls():
                try:
                    response = await client.get(feed_url)
                    response.raise_for_status()
                except Exception:
                    continue

                headline = self._extract_first_title(response.text)
                if headline:
                    collected.append(f"{feed_url} :: {headline}")

        return collected

    @classmethod
    def _feed_urls(cls) -> tuple[str, ...]:
        raw_feeds = (os.getenv("FASHION_TREND_FEEDS") or "").strip()
        if not raw_feeds:
            return cls._DEFAULT_FEEDS

        parsed = tuple(feed.strip() for feed in raw_feeds.split(",") if feed.strip())
        return parsed or cls._DEFAULT_FEEDS

    @staticmethod
    def _extract_first_title(xml_text: str) -> str | None:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return None

        item = root.find("./channel/item/title")
        if item is not None and item.text:
            return " ".join(item.text.split())

        entry = root.find("{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}title")
        if entry is None or not entry.text:
            return None
        return " ".join(entry.text.split())

    @classmethod
    def _localize_signal_for_russian(cls, signal: str) -> str:
        feed_url, _, headline = signal.partition("::")
        source = cls._source_from_url(feed_url.strip())
        normalized_headline = " ".join(headline.split())

        if cls._looks_like_english(normalized_headline):
            return f"{source}: свежий англоязычный материал"

        return f"{source}: {normalized_headline}" if normalized_headline else f"{source}: свежий материал"

    @classmethod
    def _fallback_trends(cls, season: str, year: int, source_signals: list[str]) -> str:
        localized = [cls._localize_signal_for_russian(signal) for signal in source_signals]
        today_section = localized or ["Модные медиа: свежие публикации пока недоступны"]

        lines = [
            "Сегодня:",
            *(f"• {line}" for line in today_section[:3]),
            "",
            f"Сезон ({season}):",
            "• В центре внимания фактурные слои и спокойная база.",
            "• Актуальные цвета: графит, молочный, шоколад и приглушенный синий.",
            "",
            f"Год ({year}):",
            "• Тренд на простые силуэты и акцентные аксессуары сохраняется.",
            "• Работают контрасты: мягкий трикотаж + структурная верхняя одежда.",
            "",
            "Совет: начните с нейтральной базы и добавьте один яркий акцентный цвет в аксессуарах.",
        ]
        return "\n".join(lines)

    @classmethod
    def _source_from_url(cls, url: str) -> str:
        host = urlparse(url).netloc.lower()
        return cls._SOURCE_BY_HOST.get(host, "Источник")

    @staticmethod
    def _looks_like_english(text: str) -> bool:
        latin_count = sum(1 for ch in text if "a" <= ch.lower() <= "z")
        cyrillic_count = sum(1 for ch in text if "а" <= ch.lower() <= "я" or ch.lower() == "ё")
        return latin_count > cyrillic_count

    @staticmethod
    def _season_for_month(month: int) -> str:
        if month in (12, 1, 2):
            return "зима"
        if month in (3, 4, 5):
            return "весна"
        if month in (6, 7, 8):
            return "лето"
        return "осень"
