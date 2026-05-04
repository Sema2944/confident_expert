"""Поиск похожих вещей в магазинах + партнёрская программа Admitad."""

import base64
import json
import logging
from io import BytesIO
from urllib.parse import quote_plus

import httpx
from config.settings import settings

logger = logging.getLogger(__name__)

STORES: dict[str, dict[str, str]] = {
    "lamoda": {
        "name": "Lamoda",
        "search_url": "https://www.lamoda.ru/catalogsearch/result/?q=",
        "offer_id": "lamoda",
        "emoji": "👠",
    },
    "wildberries": {
        "name": "Wildberries",
        "search_url": "https://www.wildberries.ru/catalog/0/search.aspx?search=",
        "offer_id": "wildberries",
        "emoji": "🟣",
    },
    "ozon": {
        "name": "OZON",
        "search_url": "https://www.ozon.ru/search/?text=",
        "offer_id": "ozon",
        "emoji": "🔵",
    },
}


async def describe_item_for_search(bot, file_id: str) -> dict | None:
    """Vision → JSON с search_queries для магазинов."""
    if not settings.ai_api_key:
        return None

    try:
        file = await bot.get_file(file_id)
        buf = BytesIO()
        await bot.download_file(file.file_path, buf)
        photo_bytes = buf.getvalue()
    except Exception:
        logger.exception("Failed to download photo for search")
        return None

    b64 = base64.b64encode(photo_bytes).decode("utf-8")

    content_parts = [
        {"type": "text", "text": (
            "Ты — ассистент по поиску одежды. Опиши вещь на фото для поиска в интернет-магазинах.\n"
            "Верни JSON без markdown:\n"
            '{"item_type": "...", "color": "...", "style": "...", "search_query_ru": "...", "search_query_en": "..."}\n'
            "search_query_ru — краткий запрос на русском (например: 'белая футболка oversize хлопок').\n"
            "search_query_en — краткий запрос на английском."
        )},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
    ]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.ai_api_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.ai_api_key}", "Content-Type": "application/json"},
                json={"model": settings.ai_model, "messages": [{"role": "user", "content": content_parts}], "max_tokens": 300},
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            # Пытаемся извлечь JSON из ответа
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(text)
    except Exception:
        logger.exception("Failed to describe item for search")
        return None


def build_affiliate_link(store_key: str, query: str) -> str | None:
    """Партнёрская ссылка (Admitad UID / в будущем API) или обычный поиск по магазину."""
    if store_key not in STORES:
        return None

    store = STORES[store_key]
    q = quote_plus(query)
    direct_url = store["search_url"] + q

    if settings.admitad_uid:
        encoded = quote_plus(direct_url)
        return f"https://ad.admitad.com/g/{settings.admitad_uid}/?ulp={encoded}"

    # Когда появится генерация ссылок через Admitad API — использовать admitad_api_token здесь.
    # if settings.admitad_api_token:
    #     ...

    # FALLBACK: обычный поиск (без партнёрки), работает без ключей
    if store_key == "lamoda":
        return f"https://www.lamoda.ru/search?q={q}"
    if store_key == "wildberries":
        return f"https://www.wildberries.ru/catalog/0/search.aspx?search={q}"
    if store_key == "ozon":
        return f"https://www.ozon.ru/search/?text={q}"
    return None


def build_search_results(search_data: dict) -> list[dict[str, str]]:
    """Формирует список ссылок на магазины."""
    query = search_data.get("search_query_ru", "")
    if not query:
        query = search_data.get("item_type", "одежда")

    results = []
    for store_key, store_info in STORES.items():
        url = build_affiliate_link(store_key, query)
        if url:
            results.append({
                "store": store_info["name"],
                "emoji": store_info["emoji"],
                "url": url,
            })

    return results
