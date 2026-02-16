import logging
import random

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.keyboards import menu_keyboard, occasion_keyboard, outfit_reaction_keyboard
from bot.storage import get_items
from bot.states import BotStates
from services.outfit_generation_service import OutfitResult, OutfitService
from services.outfit_service import OutfitImageService

router = Router()
outfit_service = OutfitService()
outfit_image_service = OutfitImageService()

OCCASIONS = {
    "🏢 Работа/офис": "work_office",
    "✨ Выход в люди": "going_out",
    "🎒 Спорт/прогулки": "sport_travel",
}

OCCASION_TITLES = {
    "work_office": "Рабочий образ",
    "going_out": "Образ для выхода",
    "sport_travel": "Образ для прогулки",
    "casual": "Образ",
}

COMPLIMENTS = [
    "Это спокойный и аккуратный вариант.",
    "Хороший баланс цвета.",
    "Этот вариант выглядит собранно и уверенно.",
    "Сдержанно, но стильно.",
]


async def _log_outfit_event(event_name: str, message: Message, **kwargs) -> None:
    payload = {"event": event_name, "user_id": message.from_user.id if message.from_user else None, **kwargs}
    logging.info("outfit_event %s", payload)


def _collect_outfit_file_ids(items_payload: dict[str, list[str]]) -> list[str]:
    category_order = ["top", "bottom", "dress", "outerwear", "shoes", "accessories"]
    file_ids: list[str] = []
    for category in category_order:
        file_ids.extend(items_payload.get(category, []))
    return file_ids


async def _remember_outfit(
    state: FSMContext,
    items_payload: dict[str, list[str]],
    occasion_code: str,
    season: str,
) -> None:
    await state.update_data(
        last_outfit_items_payload=items_payload,
        last_occasion_code=occasion_code,
        last_season=season,
    )


async def _send_outfit_reaction_prompt(message: Message) -> None:
    await message.answer("Что думаешь?", reply_markup=outfit_reaction_keyboard())



async def _generate_and_show_outfit(
    message: Message,
    state: FSMContext,
    occasion_code: str,
    season: str = "all",
    count: int = 1,
) -> None:
    items = get_items(message.from_user.id)
    if not items:
        await message.answer(
            "Пока в гардеробе мало вещей.\n\n"
            "Добавь хотя бы 3–5 позиций, и я смогу собрать гармоничный образ.\n"
            "Начнём?",
            reply_markup=menu_keyboard(),
        )
        await state.set_state(BotStates.menu)
        return

    outfits = await outfit_service.generate_outfits(
        items=items,
        occasion=occasion_code,
        season=season,
        count=count,
    )

    if not outfits:
        await message.answer(
            "Не удалось собрать образы: добавьте обувь и базовые категории (верх/низ или цельный образ).",
            reply_markup=menu_keyboard(),
        )
        await state.set_state(BotStates.menu)
        return

    shown_count = 0
    for outfit in outfits:
        title = OCCASION_TITLES.get(occasion_code, "Образ")
        await message.answer(title)

        outfit_image = await outfit_image_service.render_outfit_image(
            bot=message.bot,
            items_payload=outfit.items,
            image_prompt=outfit.image_prompt,
        )
        if outfit_image:
            await message.answer_photo(
                photo=BufferedInputFile(outfit_image, filename="outfit.png"),
            )
        else:
            outfit_file_ids = _collect_outfit_file_ids(outfit.items)
            if not outfit_file_ids:
                await message.answer("Не получилось показать этот образ. Попробуйте еще раз чуть позже.")
                continue

            await message.answer("Не удалось собрать единую картинку, показываю реальные вещи по очереди:")
            for file_id in outfit_file_ids:
                await message.answer_photo(photo=file_id)

        shown_count += 1
        await _remember_outfit(
            state=state,
            items_payload=outfit.items,
            occasion_code=occasion_code,
            season=season,
        )
        await _log_outfit_event("outfit_shown", message, occasion=occasion_code, season=season)
        await _send_outfit_reaction_prompt(message)

    await state.set_state(BotStates.menu)
    if shown_count > 0 and random.random() < 0.3:
        await message.answer(random.choice(COMPLIMENTS))


def _build_why_text(items_payload: dict[str, list[str]]) -> str:
    has_dress = bool(items_payload.get("dress"))
    has_outerwear = bool(items_payload.get("outerwear"))
    has_accessories = bool(items_payload.get("accessories"))

    if has_dress:
        sentences = [
            "Платье здесь работает как главный акцент, поэтому образ сразу выглядит цельным.",
            "Обувь поддерживает настроение комплекта и не спорит с основным силуэтом.",
            "Такой набор легко считывается и выглядит аккуратно в движении.",
        ]
    else:
        sentences = [
            "Верх и низ сбалансированы по роли: один элемент задаёт характер, второй удерживает образ в рамках.",
            "Обувь поддерживает общий ритм и связывает комплект в единую линию.",
            "За счёт этого образ выглядит собранно и уместно для выбранного повода.",
        ]

    if has_outerwear:
        sentences.append("Верхняя одежда добавляет глубину и делает комплект завершённым по слоям.")
    elif has_accessories:
        sentences.append("Аксессуары дают небольшой акцент и добавляют выразительность без перегруза.")

    return " ".join(sentences[:4])


@router.callback_query(F.data == "outfit:like")
async def like_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("last_outfit_items_payload"):
        await callback.answer("Не вижу последний образ…", show_alert=True)
        return

    await callback.answer()
    if callback.message:
        await callback.message.answer("Отлично. Я буду учитывать это при следующих подборках.", reply_markup=menu_keyboard())
        await _log_outfit_event("outfit_like", callback.message)


@router.callback_query(F.data == "outfit:why")
async def why_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    items_payload = data.get("last_outfit_items_payload")
    if not items_payload:
        await callback.answer("Не вижу последний образ…", show_alert=True)
        return

    await callback.answer()
    if callback.message:
        await callback.message.answer(_build_why_text(items_payload), reply_markup=outfit_reaction_keyboard())
        await _log_outfit_event("outfit_why", callback.message)


@router.callback_query(F.data == "outfit:reroll")
async def reroll_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    last_items = data.get("last_outfit_items_payload")
    occasion_code = data.get("last_occasion_code")
    season = data.get("last_season", "all")

    if not last_items or not occasion_code:
        await callback.answer("Не вижу последний образ…", show_alert=True)
        return

    await callback.answer()
    if not callback.message:
        return

    await callback.message.answer("Собираю альтернативный вариант…")
    await _log_outfit_event("outfit_reroll", callback.message, occasion=occasion_code, season=season)

    items = get_items(callback.from_user.id)
    if not items:
        await callback.message.answer(
            "Пока в гардеробе мало вещей. Добавь ещё вещи, и я соберу альтернативу.",
            reply_markup=menu_keyboard(),
        )
        return

    new_outfit: OutfitResult | None = None
    for _ in range(3):
        candidates = await outfit_service.generate_outfits(
            items=items,
            occasion=occasion_code,
            season=season,
            count=1,
        )
        if not candidates:
            break
        if candidates[0].items != last_items:
            new_outfit = candidates[0]
            break

    if new_outfit is None:
        await callback.message.answer(
            "Сейчас это самый близкий вариант… Добавь ещё вещей, чтобы я собрала более разнообразные образы.",
            reply_markup=outfit_reaction_keyboard(),
        )
        return

    title = OCCASION_TITLES.get(occasion_code, "Образ")
    await callback.message.answer(title)

    outfit_image = await outfit_image_service.render_outfit_image(
        bot=callback.message.bot,
        items_payload=new_outfit.items,
        image_prompt=new_outfit.image_prompt,
    )

    if outfit_image:
        await callback.message.answer_photo(photo=BufferedInputFile(outfit_image, filename="outfit.png"))
    else:
        outfit_file_ids = _collect_outfit_file_ids(new_outfit.items)
        if not outfit_file_ids:
            await callback.message.answer("Не получилось показать этот образ. Попробуйте еще раз чуть позже.")
            return

        await callback.message.answer("Не удалось собрать единую картинку, показываю реальные вещи по очереди:")
        for file_id in outfit_file_ids:
            await callback.message.answer_photo(photo=file_id)

    await _remember_outfit(state, new_outfit.items, occasion_code=occasion_code, season=season)
    await _log_outfit_event("outfit_shown", callback.message, occasion=occasion_code, season=season)
    await _send_outfit_reaction_prompt(callback.message)


@router.message(F.text == "👗 Собрать образы")
async def request_outfit(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.request_occasion)
    await message.answer(
        "Куда ты сегодня идёшь?\n"
        "Я подберу вариант, который будет уместным и уверенным.",
        reply_markup=occasion_keyboard(),
    )


@router.message(F.text.in_({"✨ Собрать образ", "Образы", "✨ Образы", "👗 Собрать образы"}))
async def request_outfit_short(message: Message, state: FSMContext) -> None:
    await request_outfit(message, state)


@router.message(F.text == "🔥 Сегодня")
async def outfit_today(message: Message, state: FSMContext) -> None:
    await message.answer("Секунду. Подбираю вариант на сегодня…")
    await _generate_and_show_outfit(
        message=message,
        state=state,
        occasion_code="casual",
        season="all",
        count=1,
    )


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
    await _generate_and_show_outfit(
        message=message,
        state=state,
        occasion_code=occasion,
        season="all",
        count=1,
    )
