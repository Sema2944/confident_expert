"""Визуализация образа на манекене из реальных фото пользователя.

Двухуровневая генерация:
- Trial → Flux 1.1 Pro (Replicate) — дешёвый, быстрый, приемлемое качество
- Premium → gpt-image-1 (OpenAI) — лучшее качество текстур и цветов
"""

import asyncio
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


def _build_mannequin_prompt(description: str) -> str:
    return (
        "Professional fashion photography of TWO faceless white fabric-covered mannequins "
        "standing side by side on a clean white studio background.\n"
        "LEFT mannequin: FRONT view, facing camera directly.\n"
        "RIGHT mannequin: 3/4 SIDE view, turned slightly to the right.\n\n"
        "Both mannequins wear the EXACT SAME outfit:\n"
        f"{description}\n\n"
        "Requirements:\n"
        "- Smooth egg-shaped heads, no face features\n"
        "- Metal circular base plates visible under each mannequin\n"
        "- Natural fabric draping, realistic textures and colors\n"
        "- Soft diffused studio lighting, gentle shadows\n"
        "- Clean white background\n"
        "- Photo-realistic quality, fashion catalog style"
    )


# ─── Шаг 1: Vision-описание ───────────────────────────────


async def describe_items_for_mannequin(bot, items_payload: dict[str, list[str]]) -> str:
    """Шаг 1: фото вещей → vision → детальное описание."""
    if not settings.ai_api_key:
        return ""

    all_file_ids = []
    for cat in ["top", "bottom", "dress", "onepiece", "outerwear", "shoes", "accessories"]:
        all_file_ids.extend(items_payload.get(cat, []))
    if not all_file_ids:
        return ""

    content_parts = [{"type": "text", "text": (
        "Ты модный стилист. Опиши КАЖДУЮ вещь на фото для художника, который нарисует манекен.\n"
        "Для каждой вещи укажи:\n"
        "1. Тип (футболка, джинсы, кроссовки...)\n"
        "2. Точный цвет и оттенок\n"
        "3. Материал / текстура (хлопок, деним, кожа, вязаное...)\n"
        "4. Крой и силуэт (oversize, приталенное, прямое, высокая посадка...)\n"
        "5. Детали (принт, пуговицы, молния, карманы, лейблы...)\n"
        "6. Как сидит: заправлено, навыпуск, длина\n"
        "7. Вид сбоку: профиль этой вещи\n\n"
        "Формат: пронумерованный список, по одной вещи."
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


# ─── Шаг 2: Генерация картинки ────────────────────────────


_MAX_PROMPT_LENGTH = 4000  # gpt-image-1 prompt limit


async def _generate_with_openai(prompt: str, max_retries: int = 3) -> bytes | None:
    """Генерация через gpt-image-1 (OpenAI). Премиум: ~6₽/картинка."""
    if not settings.image_api_key:
        return None

    # Truncate prompt if too long for the API
    if len(prompt) > _MAX_PROMPT_LENGTH:
        logger.warning("Truncating image prompt from %d to %d chars", len(prompt), _MAX_PROMPT_LENGTH)
        prompt = prompt[:_MAX_PROMPT_LENGTH]

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{settings.image_api_base.rstrip('/')}/images/generations",
                    headers={"Authorization": f"Bearer {settings.image_api_key}", "Content-Type": "application/json"},
                    json={"model": settings.image_model, "prompt": prompt, "n": 1, "size": "1536x1024"},
                )
                resp.raise_for_status()
                item = resp.json()["data"][0]
                b64 = item.get("b64_json")
                if b64:
                    return base64.b64decode(b64)
                # gpt-image-1 may return URL instead of b64
                image_url = item.get("url")
                if image_url:
                    img_resp = await client.get(image_url)
                    img_resp.raise_for_status()
                    return img_resp.content
                logger.error("OpenAI image response has neither b64_json nor url")
                return None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                logger.error("OpenAI image generation 400 error body: %s", e.response.text[:500])
                return None
            if e.response.status_code == 429 and attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning("OpenAI rate limited (429), retrying in %d sec (attempt %d/%d)", wait, attempt + 1, max_retries)
                await asyncio.sleep(wait)
                continue
            logger.exception("OpenAI image generation failed")
            return None
        except Exception:
            logger.exception("OpenAI image generation failed")
            return None
    return None


async def _generate_with_replicate(prompt: str) -> bytes | None:
    """Генерация через Flux 1.1 Pro (Replicate). Бюджет: ~2₽/картинка."""
    token = settings.replicate_api_token
    if not token:
        return None

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "https://api.replicate.com/v1/models/black-forest-labs/flux-1.1-pro/predictions",
                headers=headers,
                json={"input": {"prompt": prompt, "aspect_ratio": "16:9", "output_format": "png", "safety_tolerance": 5}},
            )
            resp.raise_for_status()
            prediction = resp.json()

            get_url = prediction.get("urls", {}).get("get")
            if not get_url:
                return None

            for _ in range(60):
                await asyncio.sleep(2)
                poll_resp = await client.get(get_url, headers=headers)
                poll_resp.raise_for_status()
                poll_data = poll_resp.json()
                status = poll_data.get("status")
                if status == "succeeded":
                    output = poll_data.get("output")
                    image_url = output[0] if isinstance(output, list) else output
                    if isinstance(image_url, str) and image_url.startswith("http"):
                        img_resp = await client.get(image_url)
                        img_resp.raise_for_status()
                        return img_resp.content
                    return None
                elif status == "failed":
                    logger.error("Replicate prediction failed: %s", poll_data.get("error"))
                    return None

            logger.error("Replicate prediction timed out")
            return None
    except Exception:
        logger.exception("Replicate image generation failed")
        return None


async def generate_mannequin_image(description: str, is_premium: bool = False) -> bytes | None:
    """Шаг 2: генерация манекена.

    is_premium=True  → gpt-image-1 (лучшее качество)
    is_premium=False → Flux 1.1 Pro (дешевле) с fallback на OpenAI
    """
    if not description:
        return None

    prompt = _build_mannequin_prompt(description)

    if is_premium:
        result = await _generate_with_openai(prompt)
        if result:
            return result
        return await _generate_with_replicate(prompt)
    else:
        if settings.replicate_api_token:
            result = await _generate_with_replicate(prompt)
            if result:
                return result
        return await _generate_with_openai(prompt)
