from aiogram import F, Router
from aiogram.types import Message

router = Router()


@router.message(F.text == "💳 Подписка")
async def subscription_info(message: Message) -> None:
    await message.answer(
        "Подписка на 1 месяц. Нажмите кнопку оплаты в будущем интерфейсе."
    )
