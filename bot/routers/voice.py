from aiogram import F, Router
from aiogram.types import Message

router = Router()


@router.message(F.voice)
async def voice_message(message: Message) -> None:
    await message.answer(
        "Голосовые сообщения пока не поддерживаются.\n"
        "Используй кнопки меню для выбора повода и сезона."
    )
