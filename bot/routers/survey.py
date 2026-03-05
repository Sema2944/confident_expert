import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.keyboards import menu_keyboard
from bot.states import BotStates
from bot.storage import save_survey_feedback, should_show_survey, update_survey_shown_at

router = Router()

_VALUE_OPTIONS = [
    ("outfit_matching", "Подбор образов"),
    ("ai_analysis", "AI-определение вещей"),
    ("wardrobe_mgmt", "Управление гардеробом"),
    ("weather", "Учёт погоды"),
]


def _survey_rating_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=str(i), callback_data=f"survey:rate:{i}")
        for i in range(1, 6)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        buttons,
        [InlineKeyboardButton(text="Пропустить", callback_data="survey:skip")],
    ])


def _survey_value_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"survey:value:{key}")]
        for key, label in _VALUE_OPTIONS
    ]
    rows.append([InlineKeyboardButton(text="Пропустить", callback_data="survey:skip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _survey_text_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="survey:skip")],
    ])


async def show_survey_if_eligible(bot, user_id: int) -> None:
    """Показать опрос, если пользователь не видел его последние 7 дней."""
    try:
        if not await should_show_survey(user_id):
            return
        await update_survey_shown_at(user_id)
        await bot.send_message(
            user_id,
            "Можно задам 3 быстрых вопроса? 🙏\n\n"
            "Оцени бота от 1 до 5:",
            reply_markup=_survey_rating_keyboard(),
        )
    except Exception:
        logging.exception("Failed to show survey to user %s", user_id)


@router.callback_query(F.data.startswith("survey:rate:"))
async def survey_rate(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    try:
        rating = int(callback.data.split(":")[-1])
        await state.update_data(survey_rating=rating)
        stars = "⭐" * rating
        if callback.message:
            await callback.message.edit_text(
                f"Спасибо! Ты поставил {stars}\n\n"
                "Что тебе нравится больше всего в боте?",
                reply_markup=_survey_value_keyboard(),
            )
    except Exception:
        logging.exception("Failed to handle survey rate callback")


@router.callback_query(F.data.startswith("survey:value:"))
async def survey_value(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    try:
        value_key = callback.data.split(":")[-1]
        value_label = dict(_VALUE_OPTIONS).get(value_key, value_key)
        await state.update_data(survey_most_valuable=value_label)
        await state.set_state(BotStates.survey_waiting_text)
        if callback.message:
            await callback.message.edit_text(
                f"Отлично! Выбрал: {value_label}\n\n"
                "Последний вопрос — что бы ты хотел улучшить или добавить?\n"
                "Напиши любую мысль (или пропусти):",
                reply_markup=_survey_text_keyboard(),
            )
    except Exception:
        logging.exception("Failed to handle survey value callback")


@router.callback_query(F.data == "survey:skip")
async def survey_skip(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    try:
        data = await state.get_data()
        rating = data.get("survey_rating")
        most_valuable = data.get("survey_most_valuable")
        await _finalize_survey(
            user_id=callback.from_user.id,
            bot=callback.message.bot if callback.message else None,
            state=state,
            rating=rating,
            most_valuable=most_valuable,
            free_text=None,
        )
        if callback.message:
            await callback.message.edit_text("Спасибо за отзыв! 🙏")
    except Exception:
        logging.exception("Failed to handle survey skip callback")


@router.message(BotStates.survey_waiting_text)
async def survey_free_text(message: Message, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        rating = data.get("survey_rating")
        most_valuable = data.get("survey_most_valuable")
        free_text = message.text.strip() if message.text else None
        await _finalize_survey(
            user_id=message.from_user.id,
            bot=message.bot,
            state=state,
            rating=rating,
            most_valuable=most_valuable,
            free_text=free_text,
        )
        await message.answer(
            "Спасибо за отзыв! 🙏 Это очень помогает улучшить бота.",
            reply_markup=menu_keyboard(),
        )
    except Exception:
        logging.exception("Failed to handle survey free text")


async def _finalize_survey(
    user_id: int,
    bot,
    state: FSMContext,
    rating: int | None,
    most_valuable: str | None,
    free_text: str | None,
) -> None:
    try:
        await save_survey_feedback(user_id, rating, most_valuable, free_text)
    except Exception:
        logging.exception("Failed to save survey feedback for user %s", user_id)

    if bot is not None:
        try:
            from services.admin_notify_service import AdminNotifyService
            lines = [f"📊 <b>Новый отзыв</b> от пользователя {user_id}"]
            if rating is not None:
                lines.append(f"⭐ Оценка: {rating}/5")
            if most_valuable:
                lines.append(f"💡 Нравится: {most_valuable}")
            if free_text:
                lines.append(f"💬 Комментарий: {free_text}")
            await AdminNotifyService.notify(bot, "\n".join(lines))
        except Exception:
            logging.exception("Failed to send admin survey notification")

    await state.set_state(BotStates.menu)
    await state.update_data(survey_rating=None, survey_most_valuable=None)
