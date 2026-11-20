"""MAX: подписка клуба.

create_payment в SDK ЮKassa синхронный. Здесь вызывается async start_checkout,
который внутри зовёт create_payment без await.
"""

import logging

from maxapi import Router, F
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, LinkButton

from bot_max.keyboards import _inline_kb, menu_keyboard
from config.settings import settings
from services.payment_service import is_yookassa_configured, start_checkout
from services.subscription_service import describe_offer, get_or_create_user

logger = logging.getLogger(__name__)

router = Router()


@router.message_callback(F.callback.payload == "action:subscribe")
async def cb_subscribe(event: MessageCallback, context: MemoryContext):
    await event.answer()
    user_id = event.callback.user.user_id
    chat_id = event.message.recipient.chat_id if event.message else None
    if not chat_id:
        return

    await get_or_create_user(user_id)
    offer = await describe_offer(user_id)
    if offer["active"]:
        await event.bot.send_message(
            chat_id=chat_id,
            text=offer["screen_text"],
            attachments=[menu_keyboard()],
        )
        return

    if not is_yookassa_configured():
        await event.bot.send_message(
            chat_id=chat_id,
            text=f"{offer['screen_text']}\n\nОплата скоро будет доступна.",
            attachments=[menu_keyboard()],
        )
        return

    links = []
    if offer["trial_available"]:
        trial = await start_checkout(user_id, "trial")
        if trial:
            links.append(LinkButton(
                text=f"💳 {settings.trial_days} дня за {settings.trial_price_rub} ₽",
                url=trial["confirmation_url"],
            ))
    monthly = await start_checkout(user_id, "monthly")
    if monthly:
        links.append(LinkButton(
            text=f"💳 Клуб — {offer['quote'].amount_rub} ₽",
            url=monthly["confirmation_url"],
        ))
        logger.info("MAX payment created for user %s: %s", user_id, monthly["payment_id"])

    if not links:
        await event.bot.send_message(
            chat_id=chat_id,
            text="Не удалось создать платёж. Попробуй позже.",
            attachments=[menu_keyboard()],
        )
        return

    rows = [[button] for button in links]
    await event.bot.send_message(
        chat_id=chat_id,
        text=f"{offer['screen_text']}\n\nПосле оплаты клуб включится автоматически.",
        attachments=[_inline_kb(rows)],
    )
