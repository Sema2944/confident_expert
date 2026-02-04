from aiogram import F, Router
from aiogram.types import Message

router = Router()


@router.message(F.voice)
async def voice_message(message: Message) -> None:
    await message.answer("Голос получен. Извлекаю повод и сезон...")
    await message.answer("Если не распознал, предложу выбрать кнопками.")
