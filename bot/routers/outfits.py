from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import menu_keyboard, occasion_keyboard, season_keyboard
from bot.storage import get_items
from bot.states import BotStates
from services.image_service import ImageService
from services.outfit_service import OutfitService

router = Router()
outfit_service = OutfitService()
image_service = ImageService()

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


@router.message(F.text == "Образы")
async def request_outfit_short(message: Message, state: FSMContext) -> None:
    await request_outfit(message, state)


@router.message(BotStates.request_occasion, F.text)
async def set_occasion(message: Message, state: FSMContext) -> None:
    if message.text == "⬅️ Назад":
        await state.set_state(BotStates.menu)
        await message.answer("Вернулись в меню.", reply_markup=menu_keyboard())
        return

    occasion = OCCASIONS.get(message.text)
    if not occasion:
        await message.answer("Не понял повод. Выберите кнопку.")
        return
    await state.update_data(occasion=occasion)
    await state.set_state(BotStates.request_season)
    await message.answer("Выберите сезон:", reply_markup=season_keyboard())


@router.message(BotStates.request_season, F.text)
async def set_season(message: Message, state: FSMContext) -> None:
    if message.text == "⬅️ Назад":
        await state.set_state(BotStates.request_occasion)
        await message.answer("Выберите повод:", reply_markup=occasion_keyboard())
        return

    season = SEASONS.get(message.text)
    if not season:
        await message.answer("Не понял сезон. Выберите кнопку.")
        return
    await state.update_data(season=season)

    items = get_items(message.from_user.id)
    if not items:
        await message.answer(
            "Сначала загрузите гардероб: добавьте несколько вещей, затем соберите образы.",
            reply_markup=menu_keyboard(),
        )
        await state.set_state(BotStates.menu)
        return

    outfits = await outfit_service.generate_outfits(
        items=items,
        occasion=(await state.get_data()).get("occasion", "casual"),
        season=season,
        count=3,
    )

    for index, outfit in enumerate(outfits, start=1):
        await message.answer(f"Образ {index}: {outfit.description}")
        generated = await image_service.generate_image(outfit.description)
        if generated:
            await message.answer_photo(generated)

    await state.set_state(BotStates.menu)
    await message.answer("Готово. Что делаем дальше?", reply_markup=menu_keyboard())

