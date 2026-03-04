"""Персонализированные советы на основе анализа гардероба."""

import logging

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


async def generate_personal_advice(items: list[dict]) -> str | None:
    """AI-анализ гардероба → персональные советы."""
    if not settings.ai_api_key or not items:
        return None

    summary_lines = []
    for item in items[:30]:
        parts = [
            item.get("type", ""),
            item.get("primary_color", ""),
            item.get("season", ""),
            item.get("formality", ""),
        ]
        summary_lines.append(" | ".join(p for p in parts if p and p != "unknown"))

    wardrobe_text = "\n".join(f"- {line}" for line in summary_lines if line.strip())

    prompt = f"""Ты — персональный стилист. Вот гардероб пользователя:

{wardrobe_text}

Дай 3 коротких совета (2-3 предложения каждый) на русском:
1. Цветовой совет — что добавить или как лучше сочетать цвета, которые есть
2. Стилевой совет — какого стиля не хватает или что усилить
3. Сезонный совет — готов ли гардероб к текущему/следующему сезону

Формат: эмодзи + заголовок + совет. Без нумерации. Обращайся на «ты»."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.ai_api_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.ai_api_key}", "Content-Type": "application/json"},
                json={
                    "model": settings.ai_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 500,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        logger.exception("Style advice generation failed")
        return None
