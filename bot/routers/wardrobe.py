from io import BytesIO

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import category_keyboard, menu_keyboard, photo_upload_keyboard
from bot.storage import add_item, get_category_counts
from bot.states import BotStates
from services.ai_analyze_service import AIAnalyzeService, build_russian_item_summary

router = Router()

CATEGORIES = {
    "top": "👕 Верх",
    "bottom": "👖 Низ",
    "outerwear": "🧥 Верхняя одежда",
    "shoes": "👟 Обувь",
    "accessory": "🧢 Аксессуары",
    "onepiece": "👔 Цельный образ",
}

CATEGORY_ALIASES = {
    "верх": "top",
    "👕 верх": "top",
    "низ": "bottom",
    "👖 низ": "bottom",
    "верхняя одежда": "outerwear",
    "🧥 верхняя одежда": "outerwear",
    "обувь": "shoes",
    "👟 обувь": "shoes",
    "аксессуар": "accessory",
    "аксессуары": "accessory",
    "🧢 аксессуары": "accessory",
    "платье": "onepiece",
    "цельный образ": "onepiece",
    "👔 цельный образ": "onepiece",
    "top": "top",
    "bottom": "bottom",
    "outerwear": "outerwear",
    "shoes": "shoes",
    "accessory": "accessory",
    "dress": "onepiece",
    "onepiece": "onepiece",
}


def normalize_category(text: str) -> str | None:
    cleaned = (text or "").strip().lower()
    return CATEGORY_ALIASES.get(cleaned)


@router.message(F.text == "📸 Загрузить гардероб")
async def upload_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.upload_category)
    await message.answer("Выберите категорию:", reply_markup=category_keyboard())


@router.message(F.text.in_({"📥 Загрузить", "Загрузить"}))
async def upload_start_short(message: Message, state: FSMContext) -> None:
    await upload_start(message, state)


@router.message(BotStates.upload_category, F.text)
async def set_category(message: Message, state: FSMContext) -> None:
    if message.text == "⬅️ Назад":
        await state.set_state(BotStates.menu)
        await message.answer("Вернулись в меню.", reply_markup=menu_keyboard())
        return

    category = normalize_category(message.text)
    if not category:
        await message.answer(
            "Не понял категорию. Нажмите кнопку категории ниже.",
            reply_markup=category_keyboard(),
        )
        return
    await state.update_data(category=category)
    await state.set_state(BotStates.upload_photos)
    await message.answer("Пришлите фото вещи.", reply_markup=photo_upload_keyboard())


@router.message(BotStates.upload_photos, F.photo)
async def upload_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    category = data.get("category")
    if not category:
        await state.set_state(BotStates.upload_category)
        await message.answer(
            "Сначала выберите категорию вещи.",
            reply_markup=category_keyboard(),
        )
        return

    file_id = message.photo[-1].file_id
    image_bytes = b""

    try:
        telegram_file = await message.bot.get_file(file_id)
        image_stream = BytesIO()
        await message.bot.download(telegram_file, destination=image_stream)
        image_bytes = image_stream.getvalue()
    except Exception:
        image_bytes = b""

    analyzer = AIAnalyzeService()
    analysis = await analyzer.analyze(image_bytes=image_bytes)

    add_item(
        user_id=message.from_user.id,
        category=category,
        telegram_file_id=file_id,
        item_type=analysis.type,
        primary_color=analysis.primary_color,
        secondary_color=analysis.secondary_color,
        pattern=analysis.pattern,
        season=analysis.season,
        formality=analysis.formality,
        gender_hint=analysis.gender_hint,
    )

    await message.answer(build_russian_item_summary(category=category, analysis=analysis))
    await message.answer(
        "Отправьте следующее фото или нажмите ⬅️ Назад.",
        reply_markup=photo_upload_keyboard(),
    )


@router.message(BotStates.upload_photos, F.text == "⬅️ Назад")
async def back_to_category(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.upload_category)
    await message.answer("Выберите категорию:", reply_markup=category_keyboard())


@router.message(BotStates.upload_photos)
async def upload_photo_prompt(message: Message) -> None:
    await message.answer("Нужно отправить фото.")


@router.message(F.text.in_({"🧺 Мой гардероб", "🧺 Гардероб"}))
async def wardrobe_list(message: Message) -> None:
    counts = get_category_counts(message.from_user.id)
    if not counts:
        await message.answer("Гардероб пока пуст. Нажмите 'Загрузить' и добавьте вещи.")
        return

    lines = ["Ваш гардероб:"]
    for category, count in sorted(counts.items()):
        category_name = CATEGORIES.get(category, category)
        lines.append(f"- {category_name}: {count}")
    await message.answer("\n".join(lines))
