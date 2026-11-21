"""Роутер оплаты подписки через ЮKassa."""

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.storage import set_morning_push
from config.settings import settings
from services.payment_service import (
    check_latest_user_payment,
    is_yookassa_configured,
    payment_check_text,
    start_checkout,
)
from services.subscription_service import describe_offer, get_or_create_user

router = Router()
logger = logging.getLogger(__name__)


def club_pay_keyboard(offer: dict) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if offer["trial_available"]:
        rows.append([InlineKeyboardButton(
            text=f"{settings.trial_days} дня за {settings.trial_price_rub} ₽",
            callback_data="pay:trial",
        )])
    quote = offer["quote"]
    rows.append([InlineKeyboardButton(
        text=f"Клуб — {quote.amount_rub} ₽",
        callback_data="pay:subscribe",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def club_paywall(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    offer = await describe_offer(user_id)
    return offer["paywall_text"], club_pay_keyboard(offer)


async def _send_checkout(callback: CallbackQuery, kind: str) -> None:
    if not callback.message:
        return
    if not is_yookassa_configured():
        await callback.message.answer("Оплата скоро будет доступна.")
        return
    result = await start_checkout(callback.from_user.id, kind)
    if not result:
        await callback.message.answer("Не удалось создать платёж. Попробуйте позже.")
        return
    await callback.message.answer(
        "Нажмите кнопку ниже для перехода к оплате.\n"
        "После оплаты нажмите «Я оплатил» — доступ включится, даже если уведомление задержится.\n"
        "Автосписания нет: это разовый платёж.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Перейти к оплате", url=result["confirmation_url"])],
            [InlineKeyboardButton(text="Я оплатил", callback_data="pay:check")],
        ]),
    )
    logger.info("Payment created for user %s: %s", callback.from_user.id, result["payment_id"])


@router.message(F.text.in_({"💎 Подписка", "💳 Подписка", "Подписка"}))
async def subscription_info(message: Message) -> None:
    await get_or_create_user(message.from_user.id, message.from_user.username)
    offer = await describe_offer(message.from_user.id)
    if offer["active"]:
        await message.answer(offer["screen_text"])
        return
    if not is_yookassa_configured():
        await message.answer(f"{offer['screen_text']}\n\nОплата скоро будет доступна.")
        return
    await message.answer(offer["screen_text"], reply_markup=club_pay_keyboard(offer))


@router.callback_query(F.data == "pay:subscribe")
async def pay_subscribe(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    await _send_checkout(callback, "monthly")


@router.callback_query(F.data == "pay:trial")
async def pay_trial(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    await _send_checkout(callback, "trial")


@router.callback_query(F.data == "pay:check")
async def pay_check(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    if not callback.message or not callback.from_user:
        return
    result = await check_latest_user_payment(callback.from_user.id, source="button")
    text = payment_check_text(result["outcome"], result.get("days"))
    if result["outcome"] == "canceled":
        offer = await describe_offer(callback.from_user.id)
        await callback.message.answer(text, reply_markup=club_pay_keyboard(offer))
        return
    await callback.message.answer(text)


# ── Morning push handlers ────────────────────────────────────

@router.callback_query(F.data.startswith("push:enable:"))
async def enable_push(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
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
    try:
        await callback.answer()
    except Exception:
        pass
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
    try:
        await callback.answer()
    except Exception:
        pass
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
