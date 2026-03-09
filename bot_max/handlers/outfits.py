"""MAX: подбор образов."""

import logging
import random

from maxapi import Router, F
from maxapi.context import MemoryContext
from maxapi.types import MessageCreated, MessageCallback, InputMediaBuffer

from bot.storage import get_items, log_outfit_feedback, save_outfit_to_history
from bot_max.keyboards import (
    menu_keyboard, occasion_keyboard, season_keyboard,
    outfit_reaction_keyboard, back_to_menu_keyboard,
)
from bot_max.states import MaxStates
from config.settings import settings
from services.outfit_generation_service import OutfitService
from services.subscription_service import can_generate_outfit, increment_outfit_count

logger = logging.getLogger(__name__)

router = Router()
outfit_service = OutfitService()

OCCASIONS = {
    "work_office": "Рабочий образ",
    "interview": "Образ для собеседования",
    "date": "Образ для свидания",
    "party": "Образ для вечеринки",
    "walk": "Образ для прогулки",
    "sport_active": "Спортивный образ",
}

COMPLIMENTS = [
    "Это спокойный и аккуратный вариант.",
    "Хороший баланс цвета.",
    "Этот вариант выглядит собранно и уверенно.",
    "Сдержанно, но стильно.",
]


# ─── Кнопка «Собрать образ» ────────────────────────────────

@router.message_callback(F.callback.payload == "action:outfit")
async def cb_start_outfit(event: MessageCallback, context: MemoryContext):
    await event.answer()
    user_id = event.callback.user.user_id
    chat_id = event.message.recipient.chat_id if event.message else None

    items = await get_items(user_id)
    if len(items) < 3:
        if chat_id:
            await event.bot.send_message(
                chat_id=chat_id,
                text="Добавь хотя бы 3 вещи (верх, низ, обувь) для первого образа.",
                attachments=[menu_keyboard()],
            )
        return

    allowed, reason = await can_generate_outfit(user_id)
    if not allowed:
        if chat_id:
            await event.bot.send_message(chat_id=chat_id, text=reason, attachments=[menu_keyboard()])
        return

    await context.set_state(MaxStates.request_occasion)
    if chat_id:
        await event.bot.send_message(
            chat_id=chat_id,
            text="Выбери повод:",
            attachments=[occasion_keyboard()],
        )


# ─── Выбор повода ──────────────────────────────────────────

@router.message_callback(F.callback.payload.startswith("occasion:"))
async def cb_occasion(event: MessageCallback, context: MemoryContext):
    await event.answer()
    occasion = event.callback.payload.split(":", 1)[1]
    await context.update_data(occasion=occasion)
    await context.set_state(MaxStates.request_season)

    chat_id = event.message.recipient.chat_id if event.message else None

    # Попробовать авто-сезон
    user_id = event.callback.user.user_id
    try:
        from services.weather_service import detect_season_for_user
        season, weather_msg = await detect_season_for_user(user_id)
        if season and season != "unknown":
            await context.update_data(season=season)
            await context.set_state(MaxStates.generating)
            if chat_id:
                await event.bot.send_message(
                    chat_id=chat_id,
                    text=f"🌤 {weather_msg}\n\n🔄 Подбираю образ…",
                )
            await _generate_outfit(event.bot, chat_id, user_id, context)
            return
    except Exception:
        pass

    if chat_id:
        await event.bot.send_message(
            chat_id=chat_id,
            text="Какой сезон?",
            attachments=[season_keyboard()],
        )


# ─── Выбор сезона ──────────────────────────────────────────

@router.message_callback(F.callback.payload.startswith("season:"))
async def cb_season(event: MessageCallback, context: MemoryContext):
    await event.answer()
    season = event.callback.payload.split(":", 1)[1]
    await context.update_data(season=season)
    await context.set_state(MaxStates.generating)

    user_id = event.callback.user.user_id
    chat_id = event.message.recipient.chat_id if event.message else None

    if chat_id:
        await event.bot.send_message(chat_id=chat_id, text="🔄 Подбираю образ…")

    await _generate_outfit(event.bot, chat_id, user_id, context)


# ─── Генерация образа ──────────────────────────────────────

async def _generate_outfit(bot, chat_id, user_id, context: MemoryContext):
    data = await context.get_data()
    occasion = data.get("occasion", "casual")
    season = data.get("season", "all")

    items = await get_items(user_id)
    if not items:
        if chat_id:
            await bot.send_message(chat_id=chat_id, text="Гардероб пуст.", attachments=[menu_keyboard()])
        return

    try:
        outfits = await outfit_service.generate_outfits(
            items=items, occasion=occasion, season=season, count=1, user_id=user_id,
        )
    except Exception:
        logger.exception("Outfit generation failed")
        outfits = []

    if not outfits:
        if chat_id:
            await bot.send_message(
                chat_id=chat_id,
                text="Не удалось подобрать образ. Попробуй добавить больше вещей.",
                attachments=[menu_keyboard()],
            )
        return

    outfit = outfits[0]
    title = OCCASIONS.get(occasion, "Образ")
    compliment = random.choice(COMPLIMENTS)
    text = f"✨ {title}\n\n{outfit.description}\n\n{compliment}"

    # Попытка создать коллаж
    collage_bytes = None
    try:
        from services.outfit_service import OutfitImageService
        img_svc = OutfitImageService()
        # Для MAX у нас нет Telegram file_id — используем photo_url
        # Передаём None для s3_items, коллаж попробует скачать по URL
        collage_bytes = await img_svc.render_outfit_image(
            bot=None, items_payload=outfit.items, s3_items=None,
        )
    except Exception:
        logger.debug("Collage generation failed for MAX")

    if collage_bytes and chat_id:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            attachments=[
                InputMediaBuffer(buffer=collage_bytes, filename="outfit.png"),
                outfit_reaction_keyboard(),
            ],
        )
    elif chat_id:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            attachments=[outfit_reaction_keyboard()],
        )

    # Сохранить в state и историю
    file_ids = []
    for fids in outfit.items.values():
        if isinstance(fids, list):
            file_ids.extend(fids)
    await context.update_data(
        last_outfit_items=outfit.items,
        last_occasion=occasion,
        last_season=season,
    )
    await save_outfit_to_history(user_id, file_ids, occasion, season)
    await increment_outfit_count(user_id)
    await context.set_state(MaxStates.menu)


# ─── Реакции на образ ──────────────────────────────────────

@router.message_callback(F.callback.payload == "outfit:like")
async def cb_like(event: MessageCallback, context: MemoryContext):
    await event.answer(notification="👍 Спасибо!")
    user_id = event.callback.user.user_id
    data = await context.get_data()
    await log_outfit_feedback(
        user_id, data.get("last_occasion", ""), data.get("last_season", ""),
        "like", data.get("last_outfit_items", {}),
    )
    chat_id = event.message.recipient.chat_id if event.message else None
    if chat_id:
        await event.bot.send_message(
            chat_id=chat_id,
            text="👍 Отлично! Рада, что понравилось.",
            attachments=[menu_keyboard()],
        )


@router.message_callback(F.callback.payload == "outfit:reroll")
async def cb_reroll(event: MessageCallback, context: MemoryContext):
    await event.answer()
    user_id = event.callback.user.user_id
    data = await context.get_data()
    await log_outfit_feedback(
        user_id, data.get("last_occasion", ""), data.get("last_season", ""),
        "reroll", data.get("last_outfit_items", {}),
    )
    chat_id = event.message.recipient.chat_id if event.message else None
    if chat_id:
        await event.bot.send_message(chat_id=chat_id, text="🔄 Подбираю другой вариант…")
    await _generate_outfit(event.bot, chat_id, user_id, context)
