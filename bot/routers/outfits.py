from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import occasion_keyboard, season_keyboard
from bot.states import BotStates
from bot.utils.messages import PAYWALL_MESSAGE, TRIAL_MESSAGE

router = Router()

OCCASIONS = {
    "🏢 Работа/офис": "work_office",
    "✨ Выход в люди": "going_out",
    "🎒 Спорт/прогулки": "sport_travel",
}

SEASONS = {
    "❄️ Зима": "winter",
    "🍂 Весна/осень": "demi",
    "☀️ Лето": "summer",
}


@router.message(F.text == "👗 Собрать образы")
async def request_outfit(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.request_occasion)
    await message.answer("Выберите повод:", reply_markup=occasion_keyboard())


@router.message(BotStates.request_occasion, F.text)
async def set_occasion(message: Message, state: FSMContext) -> None:
    occasion = OCCASIONS.get(message.text)
    if not occasion:
        await message.answer("Не понял повод. Выберите кнопку.")
        return
    await state.update_data(occasion=occasion)
    await state.set_state(BotStates.request_season)
    await message.answer("Выберите сезон:", reply_markup=season_keyboard())


@router.message(BotStates.request_season, F.text)
async def set_season(message: Message, state: FSMContext) -> None:
    season = SEASONS.get(message.text)
    if not season:
        await message.answer("Не понял сезон. Выберите кнопку.")
        return
    await state.update_data(season=season)

    # TODO: заменить на проверку trial/подписки в БД
    is_trial = True

    if not is_trial:
        await message.answer(PAYWALL_MESSAGE)
        await state.set_state(BotStates.menu)
        return

    await message.answer(TRIAL_MESSAGE)
    await message.answer("Образ 1: ...\nОбраз 2: ...\nОбраз 3: ...")
    await message.answer("(Тут будет 1 картинка для первого образа)")
    await state.set_state(BotStates.menu)
