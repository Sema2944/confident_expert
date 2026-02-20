from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path

import httpx

from config.settings import settings


class FashionTrendService:
    """Builds a short Russian digest for current fashion trends."""

    _PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "fashion_trends.txt"

    _SEASON_LABELS = {
        "winter": "зима", "demi": "весна/осень", "summer": "лето", "all": "текущий сезон",
    }

    async def get_trend_digest(self, season: str = "all", year: int | None = None) -> str:
        target_year = year or datetime.now().year

        # Проверяем кэш
        cached = await self._get_cached(season, target_year)
        if cached:
            return cached

        if not settings.ai_api_key:
            return self._fallback_trends(season=season, year=target_year)

        try:
            result = await self._call_ai(season=season, year=target_year)
            if result:
                await self._save_cache(season, target_year, result)
                return result
        except Exception:
            logging.exception("Fashion trend AI request failed")

        return self._fallback_trends(season=season, year=target_year)

    async def _call_ai(self, season: str, year: int) -> str | None:
        template = self._PROMPT_PATH.read_text(encoding="utf-8")
        prompt = template.format(
            source_signals="(нет внешних сигналов — используй свои знания о трендах)",
            season=self._SEASON_LABELS.get(season, season),
            year=year,
        )

        headers = {
            "Authorization": f"Bearer {settings.ai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.ai_model,
            "temperature": 0.5,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.ai_api_base.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        choices = response.json().get("choices") or []
        if not choices:
            return None
        return choices[0].get("message", {}).get("content", "").strip() or None

    async def _get_cached(self, season: str, year: int) -> str | None:
        """Проверяет кэш трендов в SQLite (если таблица существует)."""
        try:
            from bot.storage import _connect

            async with _connect() as connection:
                cursor = await connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='trend_cache'"
                )
                if not await cursor.fetchone():
                    return None

                cursor = await connection.execute(
                    """
                    SELECT digest FROM trend_cache
                    WHERE season = ? AND year = ?
                    AND cached_at > datetime('now', '-24 hours')
                    """,
                    (season, year),
                )
                row = await cursor.fetchone()
                return row["digest"] if row else None
        except Exception:
            return None

    async def _save_cache(self, season: str, year: int, digest: str) -> None:
        """Сохраняет тренды в кэш."""
        try:
            from bot.storage import _connect

            async with _connect() as connection:
                await connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trend_cache (
                        season TEXT NOT NULL,
                        year INTEGER NOT NULL,
                        digest TEXT NOT NULL,
                        cached_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (season, year)
                    )
                    """
                )
                await connection.execute(
                    """
                    INSERT OR REPLACE INTO trend_cache (season, year, digest, cached_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (season, year, digest),
                )
                await connection.commit()
        except Exception:
            logging.exception("Failed to cache trend digest")

    @classmethod
    def _fallback_trends(cls, season: str, year: int) -> str:
        season_label = cls._SEASON_LABELS.get(season, "текущий сезон")
        return (
            f"Тренды {season_label} {year}:\n"
            "- Vogue: носибельная многослойность и тихая роскошь в базе гардероба.\n"
            "- Who What Wear: шоколадные и бордовые оттенки + серый как нейтральная база.\n"
            "- Harper's Bazaar: акцентные аксессуары — крупные серьги, широкие ремни и заметные сумки.\n\n"
            "Совет: берите один заметный акцент (цвет, аксессуар или фактуру) и сочетайте с базовыми вещами.\n\n"
            "Где следить за трендами: Vogue Россия, The Blueprint, BURO."
        )
