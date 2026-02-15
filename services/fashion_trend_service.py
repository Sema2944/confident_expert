from datetime import datetime
import logging
from pathlib import Path
import xml.etree.ElementTree as ET


class FashionTrendService:
    _PROMPT_TEMPLATE = Path(__file__).resolve().parents[1] / "prompts" / "fashion_trends.txt"
    _DEFAULT_FEEDS = (
        "https://www.vogue.com/feed/rss",
        "https://www.whowhatwear.com/rss",
    )

    async def get_trend_digest(self) -> str:
        from config.settings import settings

        season = self._detect_season(datetime.now())
        year = datetime.now().year
        feed_urls = self._parse_feed_urls(settings.fashion_trend_feeds)
        source_signals = await self._collect_trend_signals(feed_urls)

        if not settings.ai_api_key:
            logging.warning("AI_API_KEY is empty; using fallback trends response.")
            return self._fallback_trends(season=season, year=year, source_signals=source_signals)

        prompt = self._load_prompt()
        if not prompt:
            return self._fallback_trends(season=season, year=year, source_signals=source_signals)

        user_prompt = prompt.format(
            season=season,
            year=year,
            source_signals=self._format_source_signals(source_signals),
        )
        payload = {
            "model": settings.ai_model,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "Authorization": f"Bearer {settings.ai_api_key}",
            "Content-Type": "application/json",
        }

        try:
            import httpx

            async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
                response = await client.post(
                    f"{settings.ai_api_base.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except Exception as error:
            logging.exception("Fashion trends request failed: %s", error)
            return self._fallback_trends(season=season, year=year, source_signals=source_signals)

        content = self._extract_content(response.json())
        if not content:
            return self._fallback_trends(season=season, year=year, source_signals=source_signals)

        return content.strip()

    @classmethod
    def _parse_feed_urls(cls, raw_feed_urls: str | None) -> tuple[str, ...]:
        if not raw_feed_urls:
            return cls._DEFAULT_FEEDS
        urls = tuple(item.strip() for item in raw_feed_urls.split(",") if item.strip())
        return urls or cls._DEFAULT_FEEDS

    async def _collect_trend_signals(self, feed_urls: tuple[str, ...]) -> list[str]:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                signals: list[str] = []
                for feed_url in feed_urls:
                    try:
                        response = await client.get(feed_url)
                        response.raise_for_status()
                    except Exception as feed_error:
                        logging.warning("Failed to fetch trends feed %s: %s", feed_url, feed_error)
                        continue

                    titles = self._extract_rss_titles(response.text, limit=3)
                    if not titles:
                        continue
                    signals.extend(f"{feed_url} :: {title}" for title in titles)
                return signals
        except Exception as error:
            logging.warning("Could not collect trend signals from feeds: %s", error)
            return []

    @staticmethod
    def _extract_rss_titles(feed_content: str, limit: int = 3) -> list[str]:
        if not feed_content.strip():
            return []

        try:
            root = ET.fromstring(feed_content)
        except ET.ParseError:
            return []

        titles: list[str] = []
        for title_node in root.findall(".//item/title"):
            if title_node.text and title_node.text.strip():
                titles.append(title_node.text.strip())
            if len(titles) >= limit:
                break

        if titles:
            return titles

        for entry_title in root.findall(".//{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}title"):
            if entry_title.text and entry_title.text.strip():
                titles.append(entry_title.text.strip())
            if len(titles) >= limit:
                break

        return titles

    @classmethod
    def _load_prompt(cls) -> str | None:
        try:
            return cls._PROMPT_TEMPLATE.read_text(encoding="utf-8").strip()
        except OSError as error:
            logging.exception("Failed to read fashion trends prompt: %s", error)
            return None

    @staticmethod
    def _extract_content(response_data: dict) -> str | None:
        choices = response_data.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message") or {}
        return message.get("content")

    @staticmethod
    def _detect_season(current_date: datetime) -> str:
        month = current_date.month
        if month in {12, 1, 2}:
            return "зима"
        if month in {3, 4, 5}:
            return "весна"
        if month in {6, 7, 8}:
            return "лето"
        return "осень"

    @staticmethod
    def _format_source_signals(source_signals: list[str]) -> str:
        if not source_signals:
            return "Нет доступных внешних сигналов по трендам."
        return "\n".join(f"- {signal}" for signal in source_signals[:8])

    @staticmethod
    def _fallback_trends(season: str, year: int, source_signals: list[str]) -> str:
        season_colors = {
            "зима": "графит, холодный синий, винный, молочный",
            "весна": "масляный жёлтый, пудровый розовый, травяной зелёный, айвори",
            "лето": "голубой, сливочный, коралловый, песочный",
            "осень": "шоколадный, оливковый, бордовый, тёплый серый",
        }
        colors = season_colors.get(season, "базовый беж, синий, белый")
        source_block = (
            "\n".join(f"• {signal}" for signal in source_signals[:4])
            if source_signals
            else "• Внешние источники временно недоступны."
        )
        return (
            f"📊 Короткий модный обзор на {season} {year}:\n"
            "Сегодня (по свежим источникам):\n"
            f"{source_block}\n"
            f"Сезонные цвета: {colors}.\n"
            "Тенденции года: мягкий тейлоринг, многослойность, аккуратные акценты цветом.\n"
            "Совет: выбери 1 трендовый цвет и сочетай его с базовыми вещами своего гардероба."
        )
