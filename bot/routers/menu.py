from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards import menu_keyboard
from bot.storage import get_items
from bot.utils.messages import HELP_MESSAGE, START_MESSAGE

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    items = get_items(message.from_user.id)
    if not items:
        await message.answer(
            f"{START_MESSAGE}\n\nКогда загрузишь вещи, нажми '🔥 Сегодня' для быстрого образа.",
            reply_markup=menu_keyboard(),
        )
        return

    await message.answer(START_MESSAGE, reply_markup=menu_keyboard())


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Меню", reply_markup=menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_MESSAGE)
