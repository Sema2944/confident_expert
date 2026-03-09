"""MAX: загрузка фото, просмотр гардероба."""

import logging

import httpx
from maxapi import Router, F
from maxapi.context import MemoryContext
from maxapi.types import MessageCreated, MessageCallback, InputMediaBuffer
from maxapi.types.attachments.image import Image as MaxImage

from bot.storage import add_item, get_items, get_wardrobe_stats
from bot_max.keyboards import menu_keyboard, back_to_menu_keyboard
from bot_max.states import MaxStates
from config.categories import CATEGORY_LABELS_RU
from config.settings import settings

logger = logging.getLogger(__name__)

router = Router()


# ─── Кнопка «Добавить вещь» ────────────────────────────────

@router.message_callback(F.callback.payload == "action:upload")
async def cb_upload(event: MessageCallback, context: MemoryContext):
    await event.answer()
    await context.set_state(MaxStates.upload_photo)
    chat_id = event.message.recipient.chat_id if event.message else None
    if chat_id:
        await event.bot.send_message(
            chat_id=chat_id,
            text="📸 Отправь фото вещи — я добавлю её в гардероб.",
            attachments=[back_to_menu_keyboard()],
        )


# ─── Приём фото ────────────────────────────────────────────

@router.message_created(F.message.body.attachments)
async def on_photo(event: MessageCreated, context: MemoryContext):
    """Пользователь отправил фото (с вложением-картинкой)."""
    attachments = event.message.body.attachments or []
    image_att = None
    for att in attachments:
        if isinstance(att, MaxImage):
            image_att = att
            break

    if not image_att:
        return  # Не изображение — пропускаем

    user_id = event.message.sender.user_id
    chat_id = event.message.recipient.chat_id

    # Скачать фото по URL
    photo_url = None
    if image_att.payload and hasattr(image_att.payload, "url"):
        photo_url = image_att.payload.url

    if not photo_url:
        await event.message.answer("Не удалось получить фото. Попробуй ещё раз.")
        return

    await event.message.answer("🔄 Анализирую вещь…")

    photo_bytes = None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(photo_url)
            resp.raise_for_status()
            photo_bytes = resp.content
    except Exception:
        logger.exception("Failed to download photo from MAX")
        await event.message.answer("Не удалось скачать фото. Попробуй ещё раз.")
        return

    # AI-анализ (если есть ключ)
    analysis = {}
    if settings.ai_api_key:
        try:
            from services.ai_analyze_service import AIAnalyzeService
            svc = AIAnalyzeService()
            analysis = await svc.analyze_item(photo_bytes) or {}
        except Exception:
            logger.exception("AI analysis failed")

    category = analysis.get("category", "top")
    item_type = analysis.get("item_name_ru") or analysis.get("type", "unknown")
    primary_color = analysis.get("primary_color", "unknown")

    # Загрузить фото в S3 (если настроено)
    s3_url = None
    try:
        from services.s3_storage_service import s3_service
        item_id_temp = 0  # placeholder, обновим после insert
        s3_url = s3_service.upload_photo(user_id, item_id_temp, photo_bytes)
    except Exception:
        pass

    item_id = await add_item(
        user_id=user_id,
        category=category,
        telegram_file_id=f"max:{user_id}:{photo_url[:60]}",  # MAX не имеет file_id как Telegram
        item_type=item_type,
        primary_color=primary_color,
        secondary_color=analysis.get("secondary_color"),
        pattern=analysis.get("pattern"),
        season=analysis.get("season"),
        formality=analysis.get("formality"),
        display_name=item_type if item_type != "unknown" else None,
        photo_url=s3_url or photo_url,
    )

    # Обновить S3 с правильным item_id
    if s3_url and item_id:
        try:
            from services.s3_storage_service import s3_service
            from bot.storage import update_photo_url
            real_url = s3_service.upload_photo(user_id, item_id, photo_bytes)
            await update_photo_url(user_id, item_id, real_url)
        except Exception:
            pass

    cat_label = CATEGORY_LABELS_RU.get(category, category)
    color_text = f" • {primary_color}" if primary_color and primary_color != "unknown" else ""
    name_text = f" • {item_type}" if item_type and item_type != "unknown" else ""

    text = f"✅ Добавлено: {cat_label}{name_text}{color_text}"

    # Подсказка
    items = await get_items(user_id)
    categories_present = {item.get("category") for item in items}
    can_build = (
        ("top" in categories_present and "bottom" in categories_present)
        or "onepiece" in categories_present
    ) and "shoes" in categories_present

    if can_build and len(items) <= 6:
        text += "\n\n🎉 Уже можно собрать образ! Нажми «✨ Собрать образ»"
    elif not can_build:
        missing = []
        if "shoes" not in categories_present:
            missing.append("обувь")
        if "onepiece" not in categories_present:
            if "top" not in categories_present:
                missing.append("верх")
            if "bottom" not in categories_present:
                missing.append("низ")
        if missing:
            text += f"\n\nДля первого образа осталось добавить: {', '.join(missing)}"

    await event.message.answer(text, attachments=[menu_keyboard()])


# ─── Кнопка «Мой гардероб» ─────────────────────────────────

@router.message_callback(F.callback.payload == "action:wardrobe")
async def cb_wardrobe(event: MessageCallback, context: MemoryContext):
    await event.answer()
    user_id = event.callback.user.user_id
    chat_id = event.message.recipient.chat_id if event.message else None

    items = await get_items(user_id)
    if not items:
        if chat_id:
            await event.bot.send_message(
                chat_id=chat_id,
                text="Гардероб пуст. Отправь фото первой вещи!",
                attachments=[menu_keyboard()],
            )
        return

    stats = await get_wardrobe_stats(user_id)
    total = stats["total_items"]
    value = stats["total_value"]

    def _w(n):
        if 11 <= n % 100 <= 19:
            return "вещей"
        last = n % 10
        if last == 1:
            return "вещь"
        if 2 <= last <= 4:
            return "вещи"
        return "вещей"

    text = f"👗 Твой гардероб\n\n📦 {total} {_w(total)}"
    if value:
        text += f" на сумму {value:,} ₽".replace(",", " ")

    text += "\n\n📊 По категориям:\n"
    for cat_key, data in stats["categories"].items():
        label = CATEGORY_LABELS_RU.get(cat_key, cat_key)
        cnt = data["count"]
        text += f"  {label}: {cnt}\n"

    if chat_id:
        await event.bot.send_message(
            chat_id=chat_id,
            text=text,
            attachments=[menu_keyboard()],
        )
