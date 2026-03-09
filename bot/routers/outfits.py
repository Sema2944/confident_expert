import logging
import random

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.keyboards import (
    after_like_keyboard, after_why_keyboard, menu_keyboard,
    occasion_keyboard, outfit_reaction_keyboard, season_keyboard,
)
from bot.storage import get_items, log_outfit_feedback, record_paywall_hit, save_outfit_to_history
from services.subscription_service import can_generate_outfit, get_or_create_user, increment_outfit_count
from config.categories import normalize_category
from config.settings import settings
from bot.states import BotStates
from services.image_service import ImageService
from services.outfit_generation_service import OutfitResult, OutfitService
from services.outfit_service import OutfitImageService
from services.outfit_visualization_service import describe_items_for_mannequin, generate_mannequin_image
from bot.utils.retry import safe_answer_photo

router = Router()
outfit_service = OutfitService()
outfit_image_service = OutfitImageService()
image_service = ImageService()

OCCASIONS = {
    "🏢 Работа/офис": "work_office",
    "💼 Собеседование": "interview",
    "💕 Свидание": "date",
    "🎉 Вечеринка": "party",
    "🚶 Прогулка": "walk",
    "🏃 Спорт": "sport_active",
    # backward compat
    "✨ Выход в люди": "going_out",
    "🎒 Спорт/прогулки": "sport_travel",
}

OCCASION_TITLES = {
    "work_office": "Рабочий образ",
    "interview": "Образ для собеседования",
    "date": "Образ для свидания",
    "party": "Образ для вечеринки",
    "walk": "Образ для прогулки",
    "sport_active": "Спортивный образ",
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
        await record_paywall_hit(message.from_user.id)
        await message.answer(
            reason,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"💎 Подписка — {settings.subscription_price} ₽/мес",
                    callback_data="pay:subscribe",
                )],
            ]),
        )
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
        user_id=message.from_user.id,
    )

    if not outfits:
        await message.answer(
            "Не удалось собрать образы: добавьте обувь и базовые категории (верх/низ или цельный образ).",
            reply_markup=menu_keyboard(),
        )
        await state.set_state(BotStates.menu)
        return

    # Для зимы: проверяем наличие верхней одежды в гардеробе
    no_outerwear_warning = (
        season == "winter"
        and not any(normalize_category(item.get("category")) == "outerwear" for item in items)
    )

    # Build file_id → (user_id, item_id) mapping for S3 authorized download
    s3_items: dict[str, tuple[int, int]] = {}
    tg_user_id = message.from_user.id
    for item in items:
        iid = item.get("id")
        if iid and item.get("photo_url"):
            for fid_key in ("processed_file_id", "telegram_file_id"):
                fid = item.get(fid_key)
                if isinstance(fid, str) and fid:
                    s3_items[fid] = (tg_user_id, iid)
                    break

    shown_count = 0
    for outfit in outfits:
        title = OCCASION_TITLES.get(occasion_code, "Образ")
        await message.answer(title)

        outfit_image = await outfit_image_service.render_outfit_image(
            bot=message.bot,
            items_payload=outfit.items,
            s3_items=s3_items or None,
        )
        if outfit_image:
            await safe_answer_photo(message,
                photo=BufferedInputFile(outfit_image, filename="outfit.png"),
            )
        else:
            outfit_file_ids = _collect_outfit_file_ids(outfit.items)
            if not outfit_file_ids:
                await message.answer("Не получилось показать этот образ. Попробуйте еще раз чуть позже.")
                continue

            await message.answer("Не удалось собрать единую картинку, показываю реальные вещи по очереди:")
            for file_id in outfit_file_ids:
                await safe_answer_photo(message, photo=file_id)

        if no_outerwear_warning:
            await message.answer(
                "⚠️ В гардеробе нет тёплой верхней одежды. "
                "Добавь пальто, куртку или пуховик — и образы станут теплее!"
            )

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
        # Сохранить образ в историю (последний из показанных)
        if outfits:
            last = outfits[-1]
            history_ids = [fid for fids in last.items.values() for fid in fids if fid]
            try:
                await save_outfit_to_history(message.from_user.id, history_ids, occasion_code, season)
            except Exception:
                logging.exception("Failed to save outfit to history")
        if random.random() < 0.3:
            await message.answer(random.choice(COMPLIMENTS))

        # Тизеры для free-пользователей
        user = await get_or_create_user(message.from_user.id)
        is_premium = user.get("subscription_status") == "active"
        count = user.get("outfit_requests_count", 0) + 1  # +1 т.к. increment ещё не отразился в объекте
        if not is_premium:
            if count == 1:
                await message.answer(
                    "💎 Кстати, с подпиской я могу показать этот образ "
                    "на манекене — в двух ракурсах, с реальными текстурами твоих вещей."
                )
            elif count == 2:
                await message.answer(
                    "💎 С подпиской ты также можешь искать похожие вещи "
                    "в Lamoda, Wildberries и OZON прямо из карточки."
                )
            elif count == 3:
                await message.answer(
                    "⚠️ Это был последний бесплатный образ.\n\n"
                    "Чтобы продолжить получать образы, визуализации на манекене "
                    "и поиск похожих вещей — оформи подписку 💎",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text=f"💎 Подписка — {settings.subscription_price} ₽/мес",
                            callback_data="pay:subscribe",
                        )],
                    ]),
                )

        # Опрос после каждого 3-го образа
        if count > 0 and count % 3 == 0:
            try:
                from bot.routers.survey import show_survey_if_eligible
                await show_survey_if_eligible(message.bot, message.from_user.id)
            except Exception:
                logging.exception("Failed to show survey after outfit")


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
    if occasion_code in ("work_office", "interview"):
        parts.append("Для офиса важна аккуратность силуэта и сдержанность — этот набор не перетягивает внимание.")
    elif occasion_code == "date":
        parts.append("На свидание важно выглядеть ухоженно и женственно — этот образ подчёркивает стиль без лишних усилий.")
    elif occasion_code == "party":
        parts.append("Для вечеринки образ должен быть запоминающимся, но гармоничным — здесь это соблюдено.")
    elif occasion_code in ("walk", "sport_travel"):
        parts.append("Для прогулки нужен комфорт и свобода движений — эти вещи позволяют чувствовать себя легко.")
    elif occasion_code == "sport_active":
        parts.append("Спортивный образ — это функциональность плюс стиль. Этот набор выглядит собранно и удобно.")
    elif occasion_code == "going_out":
        parts.append("Для выхода важно выглядеть выразительно, но не перегружено — здесь это соблюдено.")

    return "\n\n".join(parts)


@router.callback_query(F.data == "outfit:like")
async def like_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
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
            await callback.message.answer(
                "Отлично! Я буду учитывать это при следующих подборках.",
                reply_markup=after_like_keyboard(),
            )
            await _log_outfit_event("outfit_like", callback.message)
            # Опрос после первого лайка
            try:
                from bot.routers.survey import show_survey_if_eligible
                await show_survey_if_eligible(callback.message.bot, callback.from_user.id)
            except Exception:
                logging.exception("Failed to show survey after like")
    except Exception:
        logging.exception("Failed to handle outfit like callback")


@router.callback_query(F.data == "outfit:why")
async def why_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
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
                reply_markup=after_why_keyboard(),
            )
            await _log_outfit_event("outfit_why", callback.message)
    except Exception:
        logging.exception("Failed to handle outfit why callback")


@router.callback_query(F.data == "outfit:reroll")
async def reroll_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
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

        # Build file_id → (user_id, item_id) mapping for S3 authorized download
        reroll_s3_items: dict[str, tuple[int, int]] = {}
        reroll_user_id = callback.from_user.id
        for item in items:
            iid = item.get("id")
            if iid and item.get("photo_url"):
                for fid_key in ("processed_file_id", "telegram_file_id"):
                    fid = item.get(fid_key)
                    if isinstance(fid, str) and fid:
                        reroll_s3_items[fid] = (reroll_user_id, iid)
                        break

        # Collect file_ids from previous outfit to exclude
        prev_file_ids: set[str] = set()
        if last_items:
            for fids in last_items.values():
                if isinstance(fids, list):
                    prev_file_ids.update(fids)

        new_outfit: OutfitResult | None = None
        generation_error = False
        for _ in range(3):
            try:
                candidates = await outfit_service.generate_outfits(
                    items=items,
                    occasion=occasion_code,
                    season=season,
                    count=1,
                    user_id=callback.from_user.id,
                    exclude_file_ids=prev_file_ids,
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
            s3_items=reroll_s3_items or None,
        )

        if outfit_image:
            await safe_answer_photo(callback.message, photo=BufferedInputFile(outfit_image, filename="outfit.png"))
        else:
            outfit_file_ids = _collect_outfit_file_ids(new_outfit.items)
            if not outfit_file_ids:
                await callback.message.answer("Не получилось показать этот образ. Попробуйте еще раз чуть позже.")
                return

            await callback.message.answer("Не удалось собрать единую картинку, показываю реальные вещи по очереди:")
            for file_id in outfit_file_ids:
                await safe_answer_photo(callback.message, photo=file_id)

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
    try:
        await callback.answer()
    except Exception:
        pass
    try:
        if not callback.message:
            return

        data = await state.get_data()
        items_payload = data.get("last_outfit_items_payload")
        if not items_payload:
            await callback.message.answer("Не вижу последний образ для визуализации.")
            return

        user = await get_or_create_user(callback.from_user.id)
        is_premium = user.get("subscription_status") == "active"

        if not is_premium:
            await callback.message.answer(
                "✨ Визуализация на манекене — функция подписки.\n\n"
                "Хочешь увидеть, как твой образ выглядит на манекене в 2 ракурсах?\n"
                f"Оформи подписку — {settings.subscription_price} ₽/мес.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💎 Оформить подписку", callback_data="pay:subscribe")],
                ]),
            )
            return

        await callback.message.answer("Готовлю визуализацию на манекене… Это займёт 15–30 секунд.")

        description = await describe_items_for_mannequin(callback.message.bot, items_payload)
        if not description:
            # Fallback на старый метод
            image_prompt = data.get("last_image_prompt")
            if image_prompt:
                generated = await image_service.generate_image(image_prompt)
                if generated:
                    await callback.message.answer("Это стилизация по описанию. Вещи могут немного отличаться от ваших.")
                    await safe_answer_photo(callback.message,
                        photo=BufferedInputFile(generated, filename="outfit_visualization.png"),
                    )
                    await _log_outfit_event("outfit_visualize", callback.message)
                    return
            await callback.message.answer("Не удалось подготовить визуализацию. Попробуйте чуть позже.")
            return

        mannequin_image = await generate_mannequin_image(description, is_premium=is_premium)
        if not mannequin_image:
            # Fallback 1: коллаж из реальных фото
            s3_items: dict[str, tuple[int, int]] = {}
            try:
                items = await get_items(callback.from_user.id)
                for item in items:
                    iid = item.get("id")
                    if iid and item.get("photo_url"):
                        for fid_key in ("processed_file_id", "telegram_file_id"):
                            fid = item.get(fid_key)
                            if isinstance(fid, str) and fid:
                                s3_items[fid] = (callback.from_user.id, iid)
                                break
            except Exception:
                pass
            collage = await outfit_image_service.render_outfit_image(
                bot=callback.message.bot,
                items_payload=items_payload,
                s3_items=s3_items or None,
            )
            if collage:
                await safe_answer_photo(callback.message,
                    photo=BufferedInputFile(collage, filename="outfit_collage.png"),
                    caption="⏳ Визуализация на манекене временно недоступна. Вот коллаж из ваших вещей:",
                )
                await _log_outfit_event("outfit_visualize_collage_fallback", callback.message)
                return
            # Fallback 2: стилизация по описанию
            image_prompt = data.get("last_image_prompt")
            if image_prompt:
                generated = await image_service.generate_image(image_prompt)
                if generated:
                    await callback.message.answer("Это стилизация по описанию. Вещи могут немного отличаться от ваших.")
                    await safe_answer_photo(callback.message,
                        photo=BufferedInputFile(generated, filename="outfit_visualization.png"),
                    )
                    await _log_outfit_event("outfit_visualize", callback.message)
                    return
            await callback.message.answer("Не удалось подготовить визуализацию. Попробуйте чуть позже.")
            return

        quality_note = "" if is_premium else "\n\n💎 С подпиской — визуализация в премиум-качестве"
        await safe_answer_photo(callback.message,
            photo=BufferedInputFile(mannequin_image, filename="mannequin_outfit.png"),
            caption=f"✨ Твой образ на манекене — фронт и профиль{quality_note}",
        )
        await _log_outfit_event("outfit_visualize", callback.message, premium=is_premium)
    except Exception:
        logging.exception("Failed to handle outfit visualize callback")


@router.message(F.text.in_({"✨ Собрать образ", "👗 Собрать образы", "Образы"}))
async def request_outfit(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.request_occasion)
    await message.answer(
        "Куда ты сегодня идёшь?\n"
        "Я подберу вариант, который будет уместным и уверенным.",
        reply_markup=occasion_keyboard(),
    )


SEASONS = {
    "❄️ Зима": "winter",
    "🍂 Весна/осень": "demi",
    "☀️ Лето": "summer",
}


@router.message(BotStates.request_occasion, F.text)
async def set_occasion(message: Message, state: FSMContext) -> None:
    if message.text == "🏠 Меню":
        await state.set_state(BotStates.menu)
        await message.answer("Главное меню:", reply_markup=menu_keyboard())
        return

    occasion = OCCASIONS.get(message.text)
    if not occasion:
        await message.answer("Не понял повод. Выберите кнопку.")
        return

    # Авто-определение сезона по погоде
    from datetime import date
    from services.weather_service import detect_season_for_user
    season, weather_msg = await detect_season_for_user(message.from_user.id)

    data = await state.get_data()
    today = date.today().isoformat()
    if weather_msg and data.get("last_weather_date") != today:
        await message.answer(weather_msg)
        await state.update_data(last_weather_date=today)
    await _generate_and_show_outfit(
        message=message,
        state=state,
        occasion_code=occasion,
        season=season,
        count=1,
    )


@router.message(BotStates.request_season, F.text)
async def set_season(message: Message, state: FSMContext) -> None:
    if message.text == "🏠 Меню":
        await state.set_state(BotStates.menu)
        await message.answer("Главное меню:", reply_markup=menu_keyboard())
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


# ── Task 14: история образов ─────────────────────────────────────


@router.message(Command("history"))
async def cmd_outfit_history(message: Message) -> None:
    from bot.storage import get_outfit_history
    history = await get_outfit_history(message.from_user.id, days=7)

    if not history:
        await message.answer(
            "За последнюю неделю образов не было. Нажми «✨ Собрать образ»!",
            reply_markup=menu_keyboard(),
        )
        return

    lines = ["📅 Твои образы за неделю:\n"]
    for i, entry in enumerate(history[:7], 1):
        date = entry["created_at"][:10] if entry.get("created_at") else "?"
        occasion = entry.get("occasion", "?")
        liked = " ❤️" if entry.get("liked") else ""
        items_count = len(entry.get("outfit_items", []))
        lines.append(f"{i}. {date} — {occasion}, {items_count} вещей{liked}")

    await message.answer("\n".join(lines))


# ── Контекстные action-кнопки ────────────────────────────────────


@router.callback_query(F.data == "action:outfit")
async def action_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    await state.set_state(BotStates.request_occasion)
    if callback.message:
        await callback.message.answer(
            "Куда ты сегодня идёшь?\n"
            "Я подберу вариант, который будет уместным и уверенным.",
            reply_markup=occasion_keyboard(),
        )


@router.callback_query(F.data == "action:menu")
async def action_menu(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    await state.set_state(BotStates.menu)
    if callback.message:
        await callback.message.answer("Меню", reply_markup=menu_keyboard())


@router.callback_query(F.data == "action:reroll_same")
async def action_reroll_same(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    if not callback.message:
        return
    data = await state.get_data()
    occasion_code = data.get("last_occasion_code", "casual")
    await callback.message.answer("Собираю ещё один вариант…")
    from services.weather_service import detect_season_for_user
    season, _ = await detect_season_for_user(callback.from_user.id)
    await _generate_and_show_outfit(
        message=callback.message,
        state=state,
        occasion_code=occasion_code,
        season=season,
        count=1,
    )
