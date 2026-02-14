from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, Message

from bot.keyboards import menu_keyboard, occasion_keyboard, season_keyboard
from bot.storage import get_items
from bot.states import BotStates
from services.outfit_service import OutfitImageService, OutfitService

router = Router()
outfit_service = OutfitService()
outfit_image_service = OutfitImageService()

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


def _collect_outfit_file_ids(items_payload: dict[str, list[str]]) -> list[str]:
    category_order = ["top", "bottom", "dress", "outerwear", "shoes", "accessories"]
    file_ids: list[str] = []
    for category in category_order:
        file_ids.extend(items_payload.get(category, []))
    return file_ids


@router.message(F.text == "👗 Собрать образы")
async def request_outfit(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.request_occasion)
    await message.answer("Выберите повод:", reply_markup=occasion_keyboard())


@router.message(F.text.in_({"Образы", "✨ Образы", "👗 Собрать образы"}))
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
        count=1,
    )

    if not outfits:
        await message.answer(
            "Не удалось собрать образы: добавьте обувь и базовые категории (верх/низ или цельный образ).",
            reply_markup=menu_keyboard(),
        )
        await state.set_state(BotStates.menu)
        return

    for index, outfit in enumerate(outfits, start=1):
        await message.answer(f"Образ {index}: {outfit.description}")

        outfit_image = await outfit_image_service.render_outfit_image(
            bot=message.bot,
            items_payload=outfit.items,
        )
        if outfit_image:
            await message.answer_photo(
                photo=BufferedInputFile(outfit_image, filename=f"outfit_{index}.png"),
                caption="Единая картинка образа только из ваших загруженных вещей.",
            )
            continue

        outfit_file_ids = _collect_outfit_file_ids(outfit.items)
        if not outfit_file_ids:
            await message.answer("Не получилось показать этот образ. Попробуйте еще раз чуть позже.")
            continue

        await message.answer("Не удалось собрать единую картинку, показываю реальные вещи по очереди:")
        for file_id in outfit_file_ids:
            await message.answer_photo(photo=file_id)

    await state.set_state(BotStates.menu)
    await message.answer(
        "Готово. Собрал образы в одну картинку строго из ваших вещей (без добавления новых).",
        reply_markup=menu_keyboard(),
    )
