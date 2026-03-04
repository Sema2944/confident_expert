"""Роутер оплаты подписки через ЮKassa."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.storage import set_morning_push
from config.settings import settings
from services.payment_service import create_payment, is_yookassa_configured
from services.subscription_service import get_or_create_user

router = Router()
logger = logging.getLogger(__name__)


def _subscription_status_text(user: dict) -> str:
    """Формирует текст о статусе подписки."""
    if user.get("subscription_status") == "active":
        until = user.get("subscription_until", "")
        return f"✅ Подписка активна до {until[:10] if until else '—'}"
    count = user.get("outfit_requests_count", 0)
    remaining = max(0, 3 - count)
    if remaining > 0:
        return f"Пробный режим: осталось {remaining} бесплатных образов."
    return "Пробный период закончился. Оформи подписку для безлимитного доступа."


@router.message(F.text.in_({"💎 Подписка", "💳 Подписка", "Подписка"}))
async def subscription_info(message: Message) -> None:
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    status_text = _subscription_status_text(user)

    if user.get("subscription_status") == "active":
        await message.answer(f"💎 Подписка\n\n{status_text}")
        return

    if not is_yookassa_configured():
        await message.answer(
            f"💎 Подписка\n\n{status_text}\n\n"
            "Оплата скоро будет доступна."
        )
        return

    price = settings.subscription_price
    await message.answer(
        f"💎 Подписка\n\n{status_text}\n\n"
        f"Стоимость: {price} ₽ / {settings.subscription_days} дней\n"
        "Безлимитные образы, визуализация и все функции.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💳 Оплатить {price} ₽", callback_data="pay:subscribe")]
        ]),
    )


@router.callback_query(F.data == "pay:subscribe")
async def pay_subscribe(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message:
        return

    if not is_yookassa_configured():
        await callback.message.answer("Оплата скоро будет доступна.")
        return

    result = create_payment(user_id=callback.from_user.id)
    if not result:
        await callback.message.answer("Не удалось создать платёж. Попробуйте позже.")
        return

    await callback.message.answer(
        "Нажмите кнопку ниже для перехода к оплате:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Перейти к оплате", url=result["confirmation_url"])]
        ]),
    )
    logger.info("Payment created for user %s: %s", callback.from_user.id, result["payment_id"])


# ── Morning push handlers ────────────────────────────────────

@router.callback_query(F.data.startswith("push:enable:"))
async def enable_push(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message:
        return
    hour = int(callback.data.split(":")[2])
    await set_morning_push(callback.from_user.id, enabled=True, hour=hour)
    await callback.message.answer(
        f"☀️ Отлично! Каждое утро в {hour}:00 буду присылать образ по погоде.\n"
        "Отключить: /push_off",
    )


@router.callback_query(F.data == "push:select_time")
async def select_push_time(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message:
        return
    buttons = [
        [InlineKeyboardButton(text=f"{h}:00", callback_data=f"push:enable:{h}")]
        for h in [7, 8, 9, 10]
    ]
    await callback.message.answer(
        "Во сколько присылать образ?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data == "push:disable")
async def disable_push(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message:
        return
    await set_morning_push(callback.from_user.id, enabled=False)
    await callback.message.answer("Хорошо, утренние образы отключены. Включить: /push_on")


@router.message(Command("push_off"))
async def cmd_push_off(message: Message) -> None:
    await set_morning_push(message.from_user.id, enabled=False)
    await message.answer("Утренние образы отключены. Включить: /push_on")


@router.message(Command("push_on"))
async def cmd_push_on(message: Message) -> None:
    await set_morning_push(message.from_user.id, enabled=True, hour=8)
    await message.answer("☀️ Утренние образы включены — буду присылать в 8:00.")
