import logging
from io import BytesIO

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from PIL import Image

from bot.keyboards import category_keyboard, menu_keyboard, photo_upload_keyboard, wardrobe_view_keyboard
from bot.storage import (
    add_item,
    delete_item_by_id,
    get_category_counts,
    get_items,
    update_display_name,
    update_item_metadata,
    update_processed_file_id,
)
from bot.states import BotStates
from config.categories import CATEGORY_LABELS_RU, normalize_category
from services.ai_analyze_service import AIAnalyzeService, build_russian_item_summary
from services.wardrobe_analysis_service import analyze_wardrobe_gaps

router = Router()


def _item_actions_keyboard(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"item:delete:{item_id}"),
                InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"item:rename:{item_id}"),
            ],
            [
                InlineKeyboardButton(text="✨ Улучшить фото", callback_data=f"item:enhance:{item_id}"),
            ],
        ]
    )


def _confirm_delete_keyboard(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Удалить", callback_data=f"item:delete_confirm:{item_id}"),
                InlineKeyboardButton(text="↩️ Отмена", callback_data=f"item:delete_cancel:{item_id}"),
            ]
        ]
    )


def _item_title(item: dict[str, str | int | None]) -> str:
    display_name = item.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()

    item_type = (item.get("type") or "unknown").strip()
    primary_color = (item.get("primary_color") or "unknown").strip()
    if item_type != "unknown" and primary_color != "unknown":
        return f"{primary_color} {item_type}"
    if item_type != "unknown":
        return item_type
    if primary_color != "unknown":
        return primary_color
    return "вещь без названия"


_SEASON_SHORT_RU = {
    "winter": "зима", "demi": "демисезон", "summer": "лето", "all": "все сезоны",
}
_FORMALITY_SHORT_RU = {
    "sport": "спортивный", "casual": "повседневный", "smart": "smart casual", "office": "офисный",
}


def _build_item_caption(item: dict[str, str | int | None]) -> str:
    category_name = CATEGORY_LABELS_RU.get(str(item.get("category") or ""), str(item.get("category") or ""))
    first_line = f"{category_name} — {_item_title(item)}"

    season = _SEASON_SHORT_RU.get(str(item.get("season") or ""))
    formality = _FORMALITY_SHORT_RU.get(str(item.get("formality") or ""))

    if season and formality:
        return f"{first_line}\nСезон: {season} • Стиль: {formality}"
    if season:
        return f"{first_line}\nСезон: {season}"
    if formality:
        return f"{first_line}\nСтиль: {formality}"
    return first_line


def _build_enhanced_image(image_bytes: bytes) -> bytes | None:
    if not image_bytes:
        return None

    source = Image.open(BytesIO(image_bytes)).convert("RGBA")
    width, height = source.size
    px = source.load()

    corners = [px[0, 0], px[width - 1, 0], px[0, height - 1], px[width - 1, height - 1]]
    avg_r = sum(pixel[0] for pixel in corners) // 4
    avg_g = sum(pixel[1] for pixel in corners) // 4
    avg_b = sum(pixel[2] for pixel in corners) // 4

    for y in range(height):
        for x in range(width):
            r, g, b, a = px[x, y]
            distance = abs(r - avg_r) + abs(g - avg_g) + abs(b - avg_b)
            if distance < 42:
                px[x, y] = (r, g, b, 0)
            else:
                px[x, y] = (r, g, b, a)

    bbox = source.getbbox()
    if not bbox:
        return None

    cropped = source.crop(bbox)
    target_size = int(max(cropped.width, cropped.height) * 1.25)
    canvas = Image.new("RGB", (target_size, target_size), (245, 245, 245))
    offset_x = (target_size - cropped.width) // 2
    offset_y = (target_size - cropped.height) // 2
    canvas.paste(cropped, (offset_x, offset_y), cropped)

    output = BytesIO()
    canvas.save(output, format="JPEG", quality=95)
    return output.getvalue()


async def _render_wardrobe_cards(message: Message, user_id: int) -> None:
    items = await get_items(user_id)
    if not items:
        await message.answer("Гардероб пока пуст. Нажмите '📥 Добавить вещь' и добавьте вещи.")
        return

    counts = await get_category_counts(user_id)
    lines = ["Ваш гардероб:"]
    for category, count in sorted(counts.items()):
        lines.append(f"- {CATEGORY_LABELS_RU.get(category, category)}: {count}")

    gaps = analyze_wardrobe_gaps(items)
    if gaps:
        lines.append("")
        lines.append(gaps)

    await message.answer("\n".join(lines))

    for item in items:
        preview_file_id = item.get("processed_file_id") or item.get("telegram_file_id")
        caption = _build_item_caption(item)
        if preview_file_id:
            await message.answer_photo(
                photo=str(preview_file_id),
                caption=caption,
                reply_markup=_item_actions_keyboard(int(item["id"])),
            )
        else:
            await message.answer(
                f"📸 Фото недоступно\n{caption}",
                reply_markup=_item_actions_keyboard(int(item["id"])),
            )


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
        logging.exception("Failed to download photo from Telegram")
        await message.answer("❌ Не удалось загрузить фото. Попробуй ещё раз.")
        return

    analyzer = AIAnalyzeService()
    analysis = await analyzer.analyze(image_bytes=image_bytes)

    item_id = await add_item(
        user_id=message.from_user.id,
        category=category,
        telegram_file_id=file_id,
    )

    if any(
        value and value != "unknown"
        for value in [
            analysis.type,
            analysis.primary_color,
            analysis.secondary_color,
            analysis.pattern,
            analysis.season,
            analysis.formality,
            analysis.gender_hint,
        ]
    ):
        await update_item_metadata(
            user_id=message.from_user.id,
            item_id=item_id,
            metadata={
                "type": analysis.type or "unknown",
                "primary_color": analysis.primary_color or "unknown",
                "secondary_color": analysis.secondary_color or "unknown",
                "pattern": analysis.pattern or "unknown",
                "season": analysis.season or "unknown",
                "formality": analysis.formality or "unknown",
                "gender_hint": analysis.gender_hint or "unknown",
            },
        )

    await message.answer(build_russian_item_summary(category=category, analysis=analysis))

    items = await get_items(message.from_user.id)
    categories_present = {item.get("category") for item in items}
    can_build = (
        ("top" in categories_present and "bottom" in categories_present)
        or "onepiece" in categories_present
    ) and "shoes" in categories_present

    if can_build and len(items) <= 5:
        await message.answer(
            "Уже можно собрать первый образ! Нажми «✨ Собрать образ» или продолжай добавлять вещи.",
        )
    elif not can_build:
        missing = []
        if "shoes" not in categories_present:
            missing.append("обувь")
        if "onepiece" not in categories_present:
            if "top" not in categories_present:
                missing.append("верх")
            if "bottom" not in categories_present:
                missing.append("низ")
        if missing:
            await message.answer(
                f"Для первого образа осталось добавить: {', '.join(missing)}."
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
    await state.set_state(BotStates.wardrobe_view)
    await _render_wardrobe_cards(message=message, user_id=message.from_user.id)
    await message.answer("Нажмите ⬅️ Назад, чтобы вернуться в меню.", reply_markup=wardrobe_view_keyboard())


@router.callback_query(F.data.startswith("item:delete:"))
async def ask_delete_wardrobe_item(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.data or not callback.message:
        return

    item_id = int(callback.data.rsplit(":", maxsplit=1)[-1])
    await callback.message.answer(
        "Удалить эту вещь из гардероба?",
        reply_markup=_confirm_delete_keyboard(item_id),
    )


@router.callback_query(F.data.startswith("item:delete_confirm:"))
async def delete_wardrobe_item(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data or not callback.message:
        return

    item_id = int(callback.data.rsplit(":", maxsplit=1)[-1])
    removed = await delete_item_by_id(user_id=callback.from_user.id, item_id=item_id)
    if not removed:
        await callback.message.answer("Не нашла эту вещь. Обновите гардероб и попробуйте снова.")
        return
    await callback.message.answer("Удалила вещь из гардероба.")
    items_left = await get_items(callback.from_user.id)
    if not items_left:
        await state.set_state(BotStates.menu)
        await callback.message.answer("Гардероб теперь пуст.", reply_markup=menu_keyboard())
        return

    await _render_wardrobe_cards(callback.message, callback.from_user.id)


@router.callback_query(F.data.startswith("item:delete_cancel:"))
async def cancel_delete_wardrobe_item(callback: CallbackQuery) -> None:
    await callback.answer("Ок")


@router.callback_query(F.data.startswith("item:rename:"))
async def request_rename_wardrobe_item(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not callback.data or not callback.message:
        return

    item_id = int(callback.data.rsplit(":", maxsplit=1)[-1])
    await state.set_state(BotStates.wardrobe_view)
    await state.update_data(rename_item_id=item_id)
    await callback.message.answer(
        "Введите новое название вещи:",
        reply_markup=ForceReply(selective=True),
    )


@router.callback_query(F.data.startswith("item:enhance:"))
async def enhance_wardrobe_item(callback: CallbackQuery) -> None:
    await callback.answer("Обрабатываю фото…")
    if not callback.data or not callback.message:
        return

    item_id = int(callback.data.rsplit(":", maxsplit=1)[-1])
    items = await get_items(callback.from_user.id)
    item = next((entry for entry in items if entry["id"] == item_id), None)
    if not item:
        await callback.message.answer("Не нашла эту вещь. Обновите гардероб и попробуйте снова.")
        return

    try:
        source_file_id = str(item.get("telegram_file_id") or "")
        telegram_file = await callback.message.bot.get_file(source_file_id)
        image_stream = BytesIO()
        await callback.message.bot.download(telegram_file, destination=image_stream)
        processed_image = _build_enhanced_image(image_stream.getvalue())
    except Exception:
        processed_image = None

    if not processed_image:
        await callback.message.answer("Не удалось улучшить фото. Попробуйте с другим изображением.")
        return

    sent = await callback.message.answer_photo(
        photo=BufferedInputFile(processed_image, filename=f"item_{item_id}_enhanced.jpg"),
        caption="Готово! Сохранила улучшенную версию фото.",
    )
    if sent.photo:
        await update_processed_file_id(
            user_id=callback.from_user.id,
            item_id=item_id,
            file_id=sent.photo[-1].file_id,
        )


@router.message(BotStates.wardrobe_view, F.text == "⬅️ Назад")
async def wardrobe_back_to_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.menu)
    await state.update_data(rename_item_id=None)
    await message.answer("Вернулись в меню.", reply_markup=menu_keyboard())


@router.message(BotStates.wardrobe_view, F.text)
async def rename_wardrobe_item(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    item_id = data.get("rename_item_id")
    if not item_id:
        await message.answer(
            "Используйте кнопки под карточкой вещи: удалить, переименовать или улучшить фото.",
            reply_markup=wardrobe_view_keyboard(),
        )
        return

    if not message.text:
        await message.answer("Введите текстовое название вещи.")
        return

    updated = await update_display_name(
        user_id=message.from_user.id,
        item_id=int(item_id),
        display_name=message.text,
    )
    await state.update_data(rename_item_id=None)
    if not updated:
        await message.answer("Не удалось переименвать вещь. Попробуйте снова.")
        return

    await message.answer("Название обновлено.")
    await _render_wardrobe_cards(message, message.from_user.id)

