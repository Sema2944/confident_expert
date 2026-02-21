from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards import menu_keyboard
from bot.storage import get_items
from bot.utils.messages import HELP_MESSAGE, START_MESSAGE
from services.wardrobe_analysis_service import analyze_wardrobe_gaps

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    items = await get_items(message.from_user.id)
    if not items:
        await message.answer(
            f"{START_MESSAGE}\n\nКогда загрузишь вещи, нажми '✨ Собрать образ' для первого образа.",
            reply_markup=menu_keyboard(),
        )
        return

    gaps = analyze_wardrobe_gaps(items)
    if gaps:
        await message.answer(f"{START_MESSAGE}\n\n{gaps}", reply_markup=menu_keyboard())
    else:
        await message.answer(START_MESSAGE, reply_markup=menu_keyboard())


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Меню", reply_markup=menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_MESSAGE)
