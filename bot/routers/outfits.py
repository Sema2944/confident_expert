import logging
import random

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.keyboards import menu_keyboard, occasion_keyboard, outfit_reaction_keyboard, season_keyboard
from bot.storage import get_items, log_outfit_feedback
from services.subscription_service import can_generate_outfit, get_or_create_user, increment_outfit_count
from bot.states import BotStates
from services.image_service import ImageService
from services.outfit_generation_service import OutfitResult, OutfitService
from services.outfit_service import OutfitImageService

router = Router()
outfit_service = OutfitService()
outfit_image_service = OutfitImageService()
image_service = ImageService()

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
    items_details: dict[str, dict],
    occasion_code: str,
    season: str,
    image_prompt: str | None,
) -> None:
    await state.update_data(
        last_outfit_items_payload=items_payload,
        last_outfit_items_details=items_details,
        last_occasion_code=occasion_code,
        last_season=season,
        last_image_prompt=image_prompt,
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
    # Trial gating
    await get_or_create_user(message.from_user.id, message.from_user.username)
    allowed, reason = await can_generate_outfit(message.from_user.id)
    if not allowed:
        await message.answer(reason, reply_markup=menu_keyboard())
        await state.set_state(BotStates.menu)
        return

    items = await get_items(message.from_user.id)
    if not items:
        await message.answer(
            "Гардероб пуст. Добавь верх, низ и обувь — и я соберу первый образ.",
            reply_markup=menu_keyboard(),
        )
        await state.set_state(BotStates.menu)
        return

    categories_present = {item.get("category") for item in items}
    has_full_outfit = (
        ("top" in categories_present and "bottom" in categories_present)
        or "onepiece" in categories_present
    ) and "shoes" in categories_present

    if not has_full_outfit:
        missing = []
        if "shoes" not in categories_present:
            missing.append("обувь")
        if "onepiece" not in categories_present:
            if "top" not in categories_present:
                missing.append("верх")
            if "bottom" not in categories_present:
                missing.append("низ")
        await message.answer(
            f"Для образа не хватает: {', '.join(missing)}.\n"
            "Добавь — и я сразу соберу первый вариант.",
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
        # Собираем детали вещей для «Почему так»
        items_details = _extract_items_details(items, outfit.items)
        await _remember_outfit(
            state=state,
            items_payload=outfit.items,
            items_details=items_details,
            occasion_code=occasion_code,
            season=season,
            image_prompt=outfit.image_prompt,
        )
        await _log_outfit_event("outfit_shown", message, occasion=occasion_code, season=season)
        await _send_outfit_reaction_prompt(message)

    await state.set_state(BotStates.menu)

    if shown_count > 0:
        await increment_outfit_count(message.from_user.id)
        if random.random() < 0.3:
            await message.answer(random.choice(COMPLIMENTS))


_NEUTRAL_COLORS = {
    "black", "white", "gray", "grey", "navy", "beige", "brown", "cream",
    "чёрный", "белый", "серый", "бежевый", "тёмно-синий", "коричневый",
}


def _extract_items_details(
    all_items: list[dict],
    items_payload: dict[str, list[str]],
) -> dict[str, dict]:
    """Извлекает атрибуты вещей из образа для объяснения."""
    # file_id → item dict
    fid_to_item: dict[str, dict] = {}
    for item in all_items:
        for fid_key in ("processed_file_id", "telegram_file_id"):
            fid = item.get(fid_key)
            if isinstance(fid, str) and fid.strip():
                fid_to_item[fid] = item

    details: dict[str, dict] = {}
    for category, file_ids in items_payload.items():
        for fid in file_ids:
            item = fid_to_item.get(fid)
            if item:
                details[category] = {
                    "type": item.get("type"),
                    "primary_color": item.get("primary_color"),
                    "season": item.get("season"),
                    "formality": item.get("formality"),
                }
                break
    return details


def _build_why_text(
    items_details: dict[str, dict],
    occasion_code: str,
) -> str:
    """Строит объяснение на основе реальных атрибутов вещей."""
    parts = []
    occasion_label = OCCASION_TITLES.get(occasion_code, "образ")
    parts.append(f"Вот почему этот {occasion_label.lower()} работает:")

    # Анализ цветовой палитры
    colors = []
    for details in items_details.values():
        color = (details.get("primary_color") or "").strip()
        if color and color != "unknown":
            colors.append(color)

    neutral = [c for c in colors if c.lower() in _NEUTRAL_COLORS]
    accent = [c for c in colors if c.lower() not in _NEUTRAL_COLORS]

    if neutral and accent:
        parts.append(
            f"Нейтральная база ({', '.join(set(neutral))}) + акцент ({', '.join(set(accent))}) "
            "— классическое сочетание, которое всегда читается."
        )
    elif neutral and not accent:
        parts.append(f"Монохромная палитра ({', '.join(set(neutral))}) — собранный и уверенный образ.")
    elif accent:
        parts.append(f"Акцентные цвета ({', '.join(set(accent))}) задают настроение.")

    # Анализ по occasion
    if occasion_code == "work_office":
        parts.append("Для офиса важна аккуратность силуэта и сдержанность — этот набор не перетягивает внимание.")
    elif occasion_code == "going_out":
        parts.append("Для выхода важно выглядеть выразительно, но не перегружено — здесь это соблюдено.")
    elif occasion_code == "sport_travel":
        parts.append("Для прогулки нужен комфорт и свобода движений — эти вещи позволяют чувствовать себя легко.")

    return "\n\n".join(parts)


@router.callback_query(F.data == "outfit:like")
async def like_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        data = await state.get_data()
        if not data.get("last_outfit_items_payload"):
            if callback.message:
                await callback.message.answer("Не вижу последний образ…")
            return

        if callback.message:
            await log_outfit_feedback(
                user_id=callback.from_user.id,
                occasion=data.get("last_occasion_code", ""),
                season=data.get("last_season", ""),
                action="like",
                items=data["last_outfit_items_payload"],
            )
            await callback.message.answer("Отлично. Я буду учитывать это при следующих подборках.", reply_markup=menu_keyboard())
            await _log_outfit_event("outfit_like", callback.message)
    except Exception:
        logging.exception("Failed to handle outfit like callback")


@router.callback_query(F.data == "outfit:why")
async def why_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        data = await state.get_data()
        items_details = data.get("last_outfit_items_details")
        occasion_code = data.get("last_occasion_code", "casual")
        if not items_details:
            if callback.message:
                await callback.message.answer("Не вижу последний образ…")
            return

        if callback.message:
            await callback.message.answer(
                _build_why_text(items_details, occasion_code),
                reply_markup=outfit_reaction_keyboard(),
            )
            await _log_outfit_event("outfit_why", callback.message)
    except Exception:
        logging.exception("Failed to handle outfit why callback")


@router.callback_query(F.data == "outfit:reroll")
async def reroll_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        data = await state.get_data()
        last_items = data.get("last_outfit_items_payload")
        occasion_code = data.get("last_occasion_code")
        season = data.get("last_season", "all")

        if not last_items or not occasion_code:
            if callback.message:
                await callback.message.answer("Не вижу последний образ…")
            return

        await log_outfit_feedback(
            user_id=callback.from_user.id,
            occasion=occasion_code,
            season=season,
            action="reroll",
            items=last_items,
        )

        if not callback.message:
            return

        await callback.message.answer("Собираю альтернативный вариант…")
        await _log_outfit_event("outfit_reroll", callback.message, occasion=occasion_code, season=season)

        items = await get_items(callback.from_user.id)
        if not items:
            await callback.message.answer(
                "Пока в гардеробе мало вещей. Добавь ещё вещи, и я соберу альтернативу.",
                reply_markup=menu_keyboard(),
            )
            return

        new_outfit: OutfitResult | None = None
        generation_error = False
        for _ in range(3):
            try:
                candidates = await outfit_service.generate_outfits(
                    items=items,
                    occasion=occasion_code,
                    season=season,
                    count=1,
                )
            except Exception:
                logging.exception("Reroll generation failed")
                generation_error = True
                break
            if not candidates:
                break
            if candidates[0].items != last_items:
                new_outfit = candidates[0]
                break

        if generation_error:
            await callback.message.answer(
                "Ошибка при подборе. Попробуй позже.",
                reply_markup=menu_keyboard(),
            )
            return

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

        reroll_details = _extract_items_details(items, new_outfit.items)
        await _remember_outfit(
            state,
            new_outfit.items,
            items_details=reroll_details,
            occasion_code=occasion_code,
            season=season,
            image_prompt=new_outfit.image_prompt,
        )
        await _log_outfit_event("outfit_shown", callback.message, occasion=occasion_code, season=season)
        await _send_outfit_reaction_prompt(callback.message)
    except Exception:
        logging.exception("Failed to handle outfit reroll callback")


@router.callback_query(F.data == "outfit:visualize")
async def visualize_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    try:
        if not callback.message:
            return

        data = await state.get_data()
        image_prompt = data.get("last_image_prompt")
        if not image_prompt:
            await callback.message.answer("Не вижу описание последнего образа для визуализации.")
            return

        generated = await image_service.generate_image(image_prompt)
        if not generated:
            await callback.message.answer("Не удалось подготовить визуализацию. Попробуйте чуть позже.")
            return

        await callback.message.answer("Это стилизация по описанию. Вещи могут немного отличаться от ваших.")
        await callback.message.answer_photo(
            photo=BufferedInputFile(generated, filename="outfit_visualization.png"),
        )
        await _log_outfit_event("outfit_visualize", callback.message)
    except Exception:
        logging.exception("Failed to handle outfit visualize callback")


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


SEASONS = {
    "❄️ Зима": "winter",
    "🍂 Весна/осень": "demi",
    "☀️ Лето": "summer",
}


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
    await message.answer("Какой сезон?", reply_markup=season_keyboard())


@router.message(BotStates.request_season, F.text)
async def set_season(message: Message, state: FSMContext) -> None:
    if message.text == "⬅️ Назад":
        await state.set_state(BotStates.request_occasion)
        await message.answer("Куда идёшь?", reply_markup=occasion_keyboard())
        return

    season = SEASONS.get(message.text)
    if not season:
        await message.answer("Выбери сезон кнопкой.")
        return

    data = await state.get_data()
    occasion = data.get("occasion", "casual")

    await message.answer("Подбираю образ…")
    await _generate_and_show_outfit(
        message=message,
        state=state,
        occasion_code=occasion,
        season=season,
        count=1,
    )
