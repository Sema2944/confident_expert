from io import BytesIO

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import (
    category_keyboard,
    menu_keyboard,
    photo_upload_keyboard,
    wardrobe_view_keyboard,
)
from bot.storage import add_item, delete_item, get_category_counts, get_items
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


def build_wardrobe_message(user_id: int) -> str:
    counts = get_category_counts(user_id)
    items = get_items(user_id)

    lines = ["Ваш гардероб:"]
    for category, count in sorted(counts.items()):
        category_name = CATEGORIES.get(category, category)
        lines.append(f"- {category_name}: {count}")

    lines.append("")
    lines.append("Вещи:")
    for index, item in enumerate(items, start=1):
        category_name = CATEGORIES.get(item["category"], item["category"])
        color = item.get("primary_color", "unknown")
        item_type = item.get("type", "unknown")
        lines.append(f"{index}. {category_name} — {item_type}, {color}")

    lines.append("")
    lines.append("Чтобы удалить вещь, отправьте: Удалить <номер>")
    lines.append("Например: Удалить 2")
    return "\n".join(lines)


@router.message(F.text == "📸 Загрузить гардероб")
async def upload_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.upload_category)
    await message.answer("Выберите категорию:", reply_markup=category_keyboard())


@router.message(F.text.in_({"📥 Загрузить", "Загрузить", "📥 Добавить вещь"}))
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
        "Отлично. Эта вещь расширяет твои комбинации.\n"
        "Добавь ещё несколько — и образы станут разнообразнее."
    )

    items = get_items(message.from_user.id)
    if len(items) >= 5:
        await message.answer(
            "Теперь я могу собирать более точные и интересные сочетания."
        )

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
async def wardrobe_list(message: Message, state: FSMContext) -> None:
    counts = get_category_counts(message.from_user.id)
    if not counts:
        await message.answer("Гардероб пока пуст. Нажмите '📥 Добавить вещь' и добавьте вещи.")
        return

    await state.set_state(BotStates.wardrobe_view)
    await message.answer(
        build_wardrobe_message(message.from_user.id),
        reply_markup=wardrobe_view_keyboard(),
    )


@router.message(BotStates.wardrobe_view, F.text == "⬅️ Назад")
async def wardrobe_back_to_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.menu)
    await message.answer("Вернулись в меню.", reply_markup=menu_keyboard())


@router.message(BotStates.wardrobe_view, F.text.regexp(r"(?i)^удалить\s+\d+$"))
async def delete_wardrobe_item(message: Message, state: FSMContext) -> None:
    if not message.text:
        return

    _, item_number_text = message.text.strip().split(maxsplit=1)
    item_index = int(item_number_text) - 1
    removed = delete_item(message.from_user.id, item_index)
    if not removed:
        await message.answer("Не нашёл вещь с таким номером. Проверьте список и попробуйте снова.")
        return

    items_left = get_items(message.from_user.id)
    if not items_left:
        await state.set_state(BotStates.menu)
        await message.answer("Готово. Гардероб теперь пуст.", reply_markup=menu_keyboard())
        return

    await message.answer("Удалил вещь. Обновлённый список:")
    await message.answer(build_wardrobe_message(message.from_user.id), reply_markup=wardrobe_view_keyboard())


@router.message(BotStates.wardrobe_view)
async def wardrobe_view_prompt(message: Message) -> None:
    await message.answer(
        "Чтобы удалить вещь, отправьте команду в формате: Удалить 3\n"
        "Или нажмите ⬅️ Назад, чтобы вернуться в меню.",
        reply_markup=wardrobe_view_keyboard(),
    )
