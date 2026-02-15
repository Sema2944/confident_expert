from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import menu_keyboard
from bot.states import BotStates
from bot.storage import add_feedback

router = Router()


@router.message(Command("feedback"))
@router.message(F.text == "📝 Обратная связь")
async def start_feedback(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.feedback_waiting_text)
    await message.answer(
        "Напишите, что улучшить в боте или какие функции добавить. "
        "Можно одним сообщением в свободной форме.",
    )


@router.message(BotStates.feedback_waiting_text, F.text)
async def save_feedback(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip():
        await message.answer("Нужен текст. Напишите отзыв одним сообщением.")
        return

    add_feedback(
        user_id=message.from_user.id,
        text=message.text,
        contact=message.from_user.username,
    )
    await state.set_state(BotStates.menu)
    await message.answer(
        "Спасибо! Отзыв сохранён. Это помогает готовить масштабирование и улучшать качество.",
        reply_markup=menu_keyboard(),
    )
