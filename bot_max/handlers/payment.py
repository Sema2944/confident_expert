"""MAX: подписка."""

import logging

from maxapi import Router, F
from maxapi.context import MemoryContext
from maxapi.types import MessageCallback, LinkButton

from bot.storage import _connect, _ph
from bot_max.keyboards import _inline_kb, menu_keyboard
from services.subscription_service import get_or_create_user
from services.payment_service import create_subscription_payment

logger = logging.getLogger(__name__)

router = Router()


@router.message_callback(F.callback.payload == "action:subscribe")
async def cb_subscribe(event: MessageCallback, context: MemoryContext):
    await event.answer()
    user_id = event.callback.user.user_id
    chat_id = event.message.recipient.chat_id if event.message else None
    if not chat_id:
        return

    user = await get_or_create_user(user_id)
    if user.get("subscription_status") == "active":
        await event.bot.send_message(
            chat_id=chat_id,
            text="✅ Подписка уже активна!",
            attachments=[menu_keyboard()],
        )
        return

    # Создать платёж
    result = await create_subscription_payment(user_id=user_id)
    if result:
        kb = _inline_kb([
            [LinkButton(text="💳 Оплатить 399 ₽", url=result["confirmation_url"])],
        ])
        await event.bot.send_message(
            chat_id=chat_id,
            text=(
                "💎 Подписка «Шкаф Работает»\n\n"
                "399 ₽/мес — безлимитные образы\n"
                "После оплаты подписка активируется автоматически."
            ),
            attachments=[kb],
        )
    else:
        await event.bot.send_message(
            chat_id=chat_id,
            text="Не удалось создать платёж. Попробуй позже.",
            attachments=[menu_keyboard()],
        )
