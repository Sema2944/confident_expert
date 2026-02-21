"""Визуализация образа на манекене из реальных фото пользователя."""

import base64
import logging
from io import BytesIO
import httpx
from config.settings import settings

logger = logging.getLogger(__name__)


async def download_telegram_photo(bot, file_id: str) -> bytes:
    file = await bot.get_file(file_id)
    buf = BytesIO()
    await bot.download_file(file.file_path, buf)
    return buf.getvalue()


def prepare_photo_for_api(photo_bytes: bytes) -> str:
    return base64.b64encode(photo_bytes).decode("utf-8")


async def describe_items_for_mannequin(bot, items_payload: dict[str, list[str]]) -> str:
    """Шаг 1: фото вещей → gpt-4o vision → детальное описание."""
    if not settings.ai_api_key:
        return ""

    all_file_ids = []
    for cat in ["top", "bottom", "dress", "onepiece", "outerwear", "shoes", "accessories"]:
        all_file_ids.extend(items_payload.get(cat, []))
    if not all_file_ids:
        return ""

    content_parts = [{"type": "text", "text": (
        "Ты модный стилист. Опиши КАЖДУЮ вещь на фото для художника, который нарисует манекен.\n"
        "Для каждой вещи: тип, точный цвет, материал/текстура, крой/силуэт, детали, как сидит, вид сбоку.\n"
        "Формат: пронумерованный список."
    )}]

    for file_id in all_file_ids[:5]:
        try:
            photo_bytes = await download_telegram_photo(bot, file_id)
            b64 = prepare_photo_for_api(photo_bytes)
            content_parts.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        except Exception:
            logger.exception("Failed to download photo %s", file_id)

    if len(content_parts) < 2:
        return ""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.ai_api_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.ai_api_key}", "Content-Type": "application/json"},
                json={"model": settings.ai_model, "messages": [{"role": "user", "content": content_parts}], "max_tokens": 800},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        logger.exception("Vision description failed")
        return ""


async def generate_mannequin_image(description: str) -> bytes | None:
    """Шаг 2: описание → gpt-image-1 → манекен фронт + профиль."""
    if not settings.image_api_key or not description:
        return None

    prompt = (
        "Professional fashion photography of TWO faceless white fabric-covered mannequins side by side "
        "on clean white studio background. LEFT: front view. RIGHT: 3/4 side view. "
        "Both wear the EXACT SAME outfit:\n"
        f"{description}\n\n"
        "Smooth egg-shaped heads, metal base plates, natural fabric draping, "
        "realistic textures, soft studio lighting, photo-realistic quality."
    )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.image_api_base.rstrip('/')}/images/generations",
                headers={"Authorization": f"Bearer {settings.image_api_key}", "Content-Type": "application/json"},
                json={"model": settings.image_model, "prompt": prompt, "n": 1, "size": "1792x1024", "response_format": "b64_json"},
            )
            resp.raise_for_status()
            return base64.b64decode(resp.json()["data"][0]["b64_json"])
    except Exception:
        logger.exception("Mannequin generation failed")
        return None
