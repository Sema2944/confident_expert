"""Роутер поиска похожих вещей в магазинах."""

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.storage import get_items
from config.settings import settings
from services.subscription_service import get_or_create_user
from services.visual_search_service import build_search_results, describe_item_for_search

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("find_similar:"))
async def find_similar_item(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    if not callback.data or not callback.message:
        return

    user = await get_or_create_user(callback.from_user.id)
    is_premium = user.get("subscription_status") == "active"

    if not is_premium:
        await callback.message.answer(
            "🔍 Поиск похожих вещей — функция подписки.\n\n"
            "Я найду похожие вещи в Lamoda, Wildberries и OZON с прямыми ссылками.\n"
            f"Оформи подписку — {settings.subscription_price} ₽/мес.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 Оформить подписку", callback_data="pay:subscribe")],
            ]),
        )
        return

    item_id = int(callback.data.split(":", 1)[1])
    items = await get_items(callback.from_user.id)
    item = next((entry for entry in items if entry["id"] == item_id), None)
    if not item:
        await callback.message.answer("Не нашла эту вещь. Обновите гардероб.")
        return

    file_id = item.get("processed_file_id") or item.get("telegram_file_id")
    if not file_id:
        await callback.message.answer("Нет фото для поиска.")
        return

    await callback.message.answer("🔍 Ищу похожие вещи в магазинах…")

    search_data = await describe_item_for_search(callback.message.bot, str(file_id))
    if not search_data:
        # Fallback — используем данные из карточки
        item_type = item.get("type", "")
        color = item.get("primary_color", "")
        query = f"{color} {item_type}".strip() or "одежда"
        search_data = {"search_query_ru": query}

    results = build_search_results(search_data)
    if not results:
        await callback.message.answer("Не удалось подготовить ссылки для поиска.")
        return

    buttons = [
        [InlineKeyboardButton(text=f"{r['emoji']} {r['store']}", url=r["url"])]
        for r in results
    ]

    await callback.message.answer(
        "🔍 Похожие вещи в магазинах:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
