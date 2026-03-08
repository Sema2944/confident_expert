from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config.settings import settings
from services.subscription_service import activate_subscription

router = Router()


@router.message(Command("gift_premium"))
async def gift_premium(message: Message):
    if message.from_user.id != settings.admin_id:
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer(
            "Использование: /gift_premium <user_id> [дней]\n"
            "Пример: /gift_premium 123456789 90"
        )
        return

    try:
        target_user_id = int(args[1])
        days = int(args[2]) if len(args) > 2 else 30
    except ValueError:
        await message.answer("Неверный формат. Пример: /gift_premium 123456789 90")
        return

    await activate_subscription(target_user_id, days)
    await message.answer(f"✅ Премиум на {days} дней выдан пользователю {target_user_id}")

    try:
        await message.bot.send_message(
            target_user_id,
            f"🎁 Вам подарена премиум-подписка на {days} дней! Все функции разблокированы.",
        )
    except Exception:
        pass
