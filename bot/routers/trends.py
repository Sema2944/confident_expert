from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards import menu_keyboard
from services.fashion_trend_service import FashionTrendService

router = Router()
fashion_trend_service = FashionTrendService()


@router.message(Command("trends"))
async def cmd_trends(message: Message) -> None:
    await send_trends(message)


@router.message(F.text.in_({"🔥 Тренды", "🎨 Модные тренды", "🎨 Тренды", "Тренды", "Мода", "Цвета сезона"}))
async def trends_from_menu(message: Message) -> None:
    await send_trends(message)


async def send_trends(message: Message) -> None:
    await message.answer("Собираю актуальные модные тренды...", reply_markup=menu_keyboard())
    trends_text = await fashion_trend_service.get_trend_digest()
    await message.answer(trends_text, reply_markup=menu_keyboard())
