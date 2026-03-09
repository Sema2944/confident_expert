import logging
from io import BytesIO

from aiogram import F, Router
from aiogram.filters import Command
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

from bot.keyboards import (
    after_upload_keyboard, category_keyboard, menu_keyboard, photo_upload_keyboard,
    wardrobe_view_keyboard, confirm_ai_keyboard, manual_category_keyboard,
    subcategory_keyboard, color_keyboard, season_inline_keyboard, formality_keyboard,
    wardrobe_filter_keyboard, capsule_list_keyboard, capsule_detail_keyboard,
    capsule_add_item_keyboard, capsule_item_keyboard, after_upload_capsule_keyboard,
)
from config.settings import settings
from bot.storage import (
    add_item,
    add_item_to_capsule,
    delete_capsule,
    delete_item_by_id,
    get_capsule_by_id,
    get_capsule_items,
    get_category_counts,
    get_items,
    get_user_capsules,
    get_wardrobe_stats,
    remove_item_from_capsule,
    update_display_name,
    update_item_metadata,
    update_item_price,
    update_photo_url,
    update_processed_file_id,
)
from bot.states import BotStates
from config.categories import CATEGORY_LABELS_RU, normalize_category
from services.ai_analyze_service import AIAnalyzeService, build_russian_item_summary
from services.wardrobe_analysis_service import analyze_wardrobe_gaps, analyze_wardrobe_gaps_with_actions
from services.visual_search_service import build_affiliate_link
from bot.utils.retry import safe_answer_photo

router = Router()


async def _safe_answer(callback: CallbackQuery, text: str = "", show_alert: bool = False) -> None:
    """Wrapper around callback.answer() that ignores errors from expired callbacks."""
    try:
        if text:
            await callback.answer(text, show_alert=show_alert)
        else:
            await _safe_answer(callback)
    except Exception:
        pass


def _item_actions_keyboard(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"item:delete:{item_id}"),
                InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"item:rename:{item_id}"),
            ],
            [
                InlineKeyboardButton(text="✨ Улучшить фото", callback_data=f"item:enhance:{item_id}"),
                InlineKeyboardButton(text="💰 Указать цену", callback_data=f"set_price:{item_id}"),
            ],
            [
                InlineKeyboardButton(text="🔍 Найти похожее", callback_data=f"find_similar:{item_id}"),
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


def _format_price(value: int) -> str:
    return f"{value:,} ₽".replace(",", " ")


async def _check_first_outfit_trigger(message: Message, user_id: int) -> None:
    """После загрузки вещи — проверить, можно ли собрать первый образ (Task 12)."""
    items = await get_items(user_id)
    categories = {item.get("category") for item in items}

    if len(items) == 1:
        cat_label = CATEGORY_LABELS_RU.get(str(items[0].get("category") or ""), "вещь")
        await message.answer(
            f"👍 Первая вещь добавлена! Добавь ещё хотя бы одну — и я покажу, что можно собрать."
        )
    elif len(items) == 2 and ("top" in categories or "onepiece" in categories) and "bottom" in categories:
        await message.answer(
            "🎉 Отлично! У тебя уже есть верх и низ — могу собрать первый образ!\n\n"
            "👟 Добавь обувь для полного образа, или нажми «✨ Собрать образ» прямо сейчас.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✨ Собрать первый образ!", callback_data="outfit:quick_first")],
                [InlineKeyboardButton(text="📥 Сначала добавлю обувь", callback_data="continue_upload")],
            ]),
        )


async def _suggest_capsules_for_item(message: Message, user_id: int, item_id: int) -> None:
    """After uploading an item, suggest adding it to matching capsules."""
    capsules = await get_user_capsules(user_id)
    if not capsules:
        await message.answer("Что дальше?", reply_markup=after_upload_keyboard())
        return
    # Get item details
    items = await get_items(user_id)
    item = next((it for it in items if it.get("id") == item_id), None)
    if not item:
        await message.answer("Что дальше?", reply_markup=after_upload_keyboard())
        return
    from services.capsule_service import suggest_capsules_for_item
    suggestions = suggest_capsules_for_item(item)
    matching = [c["name"] for c in capsules if c["name"] in suggestions]
    if matching:
        await message.answer(
            "💊 Добавить в капсулу?",
            reply_markup=after_upload_capsule_keyboard(matching, item_id),
        )
    else:
        await message.answer("Что дальше?", reply_markup=after_upload_keyboard())


_CAT_EMOJI = {
    "top": "👕", "bottom": "👖", "outerwear": "🧥",
    "shoes": "👟", "accessories": "🧢", "onepiece": "👔",
}
_CAT_SHORT = {
    "top": "Верх", "bottom": "Низ", "outerwear": "Верхняя",
    "shoes": "Обувь", "accessories": "Аксессуары", "onepiece": "Цельный",
}
_WARDROBE_PAGE_SIZE = 5


def _wardrobe_categories_keyboard(cat_counts: dict[str, int]) -> InlineKeyboardMarkup:
    """Inline-клавиатура с категориями гардероба."""
    rows: list[list[InlineKeyboardButton]] = []
    cats = list(cat_counts.items())
    for i in range(0, len(cats), 2):
        row = []
        for cat, cnt in cats[i:i + 2]:
            emoji = _CAT_EMOJI.get(cat, "📦")
            short = _CAT_SHORT.get(cat, cat)
            row.append(InlineKeyboardButton(
                text=f"{emoji} {short} ({cnt})",
                callback_data=f"wardrobe:cat:{cat}",
            ))
        rows.append(row)
    rows.append([
        InlineKeyboardButton(text="📊 Все вещи", callback_data="wardrobe:all"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="action:menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _wardrobe_page_keyboard(category: str | None, page: int, total: int) -> InlineKeyboardMarkup:
    """Пагинация для списка вещей в гардеробе."""
    total_pages = (total + _WARDROBE_PAGE_SIZE - 1) // _WARDROBE_PAGE_SIZE
    nav_row: list[InlineKeyboardButton] = []
    cat_part = category or "all"
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"wardrobe:page:{cat_part}:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="▶️ Дальше", callback_data=f"wardrobe:page:{cat_part}:{page + 1}"))
    rows = []
    if nav_row:
        rows.append(nav_row)
    rows.append([
        InlineKeyboardButton(text="👗 К категориям", callback_data="wardrobe:back"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="action:menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _item_line(idx: int, item: dict) -> str:
    """Одна строка вещи в текстовом списке."""
    title = _item_title(item)
    color = item.get("primary_color") or ""
    formality = _FORMALITY_SHORT_RU.get(str(item.get("formality") or ""), "")
    season = _SEASON_SHORT_RU.get(str(item.get("season") or ""), "")
    parts = [p for p in [color, formality, season] if p and p != "unknown"]
    detail = " · ".join(parts)
    suffix = f" — {detail}" if detail else ""
    return f"{idx}. {title}{suffix}"


def _item_detail_keyboard(item_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для карточки конкретной вещи."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"item:delete:{item_id}"),
            InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"item:rename:{item_id}"),
        ],
        [
            InlineKeyboardButton(text="🔍 Найти похожее", callback_data=f"find_similar:{item_id}"),
        ],
        [
            InlineKeyboardButton(text="👗 К категориям", callback_data="wardrobe:back"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="action:menu"),
        ],
    ])


async def _render_wardrobe_overview(message: Message, user_id: int) -> None:
    """Показать статистику гардероба + кнопки категорий (без фото)."""
    items = await get_items(user_id)
    if not items:
        await message.answer("Гардероб пока пуст. Нажмите '📥 Добавить вещь' и добавьте вещи.")
        return

    stats = await get_wardrobe_stats(user_id)
    total = stats["total_items"]
    w = "вещь" if total % 10 == 1 and total % 100 != 11 else (
        "вещи" if 2 <= total % 10 <= 4 and not 12 <= total % 100 <= 14 else "вещей"
    )

    lines = [f"👗 Твой гардероб ({total} {w})", ""]

    cat_counts: dict[str, int] = {}
    if stats["categories"]:
        for cat, info in stats["categories"].items():
            cnt = info["count"]
            cat_counts[cat] = cnt
            emoji = _CAT_EMOJI.get(cat, "📦")
            label = _CAT_SHORT.get(cat, cat)
            lines.append(f"{emoji} {label}: {cnt} шт.")

    lines.append("")
    lines.append("Выбери категорию чтобы посмотреть вещи:")

    await message.answer(
        "\n".join(lines),
        reply_markup=_wardrobe_categories_keyboard(cat_counts),
    )


async def _render_wardrobe_page(message: Message, user_id: int, category: str | None, page: int) -> None:
    """Показать страницу вещей (текст, без фото)."""
    items = await get_items(user_id)
    if category:
        items = [i for i in items if i.get("category") == category]

    total = len(items)
    if not items:
        label = CATEGORY_LABELS_RU.get(category, category) if category else "Все вещи"
        await message.answer(f"{label}: пусто")
        return

    total_pages = (total + _WARDROBE_PAGE_SIZE - 1) // _WARDROBE_PAGE_SIZE
    start = page * _WARDROBE_PAGE_SIZE
    page_items = items[start:start + _WARDROBE_PAGE_SIZE]

    if category:
        emoji = _CAT_EMOJI.get(category, "📦")
        label = CATEGORY_LABELS_RU.get(category, category)
        header = f"{emoji} {label} ({total} вещей) — стр. {page + 1}/{total_pages}"
    else:
        header = f"📊 Все вещи ({total}) — стр. {page + 1}/{total_pages}"

    lines = [header, ""]
    for i, item in enumerate(page_items, start=start + 1):
        item_id = item.get("id")
        line = _item_line(i, item)
        lines.append(line)
        # Add inline button to view item detail
        lines.append(f"   → /item_{item_id}")

    # Item buttons for quick access
    item_buttons: list[list[InlineKeyboardButton]] = []
    for item in page_items:
        item_id = int(item["id"])
        title = _item_title(item)
        item_buttons.append([
            InlineKeyboardButton(
                text=f"📋 {title[:30]}",
                callback_data=f"wardrobe:item:{item_id}",
            )
        ])

    nav_kb = _wardrobe_page_keyboard(category, page, total)
    # Merge item buttons + nav buttons
    all_buttons = item_buttons + nav_kb.inline_keyboard
    kb = InlineKeyboardMarkup(inline_keyboard=all_buttons)

    await message.answer("\n".join(lines), reply_markup=kb)


@router.message(F.text == "📸 Загрузить гардероб")
async def upload_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.upload_category)
    await message.answer("Выберите категорию:", reply_markup=category_keyboard())


@router.message(F.text.in_({"📥 Загрузить", "Загрузить", "📥 Добавить вещь"}))
async def upload_start_short(message: Message, state: FSMContext) -> None:
    await upload_start(message, state)

@router.message(BotStates.upload_category, F.text)
async def set_category(message: Message, state: FSMContext) -> None:
    if message.text == "🏠 Меню":
        await state.set_state(BotStates.menu)
        await message.answer("Главное меню:", reply_markup=menu_keyboard())
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

    items = await get_items(message.from_user.id)
    if not items:
        await message.answer(
            "📸 Совет: как фоткать вещи\n\n"
            "Лучший способ — разложи вещь ровно на полу или кровати и сфоткай сверху. "
            "Так бот точнее определит цвет и стиль.\n\n"
            "✅ Хорошо:\n"
            "- Ровно разложена на светлом фоне\n"
            "- Одна вещь — одно фото\n"
            "- Хорошее освещение\n\n"
            "❌ Плохо:\n"
            "- Скомканная / в шкафу\n"
            "- Тёмное фото\n"
            "- Несколько вещей сразу\n\n"
            "Отправляй фото 👇",
            reply_markup=photo_upload_keyboard(),
        )
    else:
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

    # Photo quality gate
    if analysis.photo_quality == "unclear":
        await message.answer(
            "🤔 Не удалось понять что на фото. Попробуй:\n"
            "- Сфоткать только одну вещь\n"
            "- Разложить ровно на полу\n"
            "- При хорошем освещении",
            reply_markup=photo_upload_keyboard(),
        )
        return

    ai_success = any(
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
    )

    # Сохраняем file_id для дальнейшего использования
    await state.update_data(manual_file_id=file_id, manual_ai_category=category)

    if ai_success:
        # AI успешно распознал — сохраняем предварительно и предлагаем подтвердить
        item_id = await add_item(
            user_id=message.from_user.id,
            category=category,
            telegram_file_id=file_id,
        )
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
        if analysis.display_name:
            await update_display_name(
                user_id=message.from_user.id,
                item_id=item_id,
                display_name=analysis.display_name,
            )
        await state.update_data(ai_saved_item_id=item_id)

        # Upload compressed photo to S3 (non-blocking: errors don't break flow)
        try:
            from services.s3_storage_service import s3_service
            if s3_service.enabled:
                photo_url = s3_service.upload_photo(message.from_user.id, item_id, image_bytes)
                if photo_url:
                    await update_photo_url(message.from_user.id, item_id, photo_url)
        except Exception:
            logging.exception("S3 upload failed, continuing without S3")

        summary = build_russian_item_summary(category=category, analysis=analysis)

        if analysis.photo_quality == "poor":
            await message.answer(
                "📸 Фото не очень чёткое — бот мог ошибиться с цветом или типом.\n\n"
                "Совет: разложи вещь ровно на светлом фоне и сфоткай сверху. "
                "Но если всё верно — просто подтверди 👇"
            )

        # Генерируем карточку вещи в Pinterest-стиле
        try:
            from services.item_card_service import ItemCardService
            cat_label = CATEGORY_LABELS_RU.get(category, "")
            parts = cat_label.split(" ", 1)
            cat_emoji = parts[0] if len(parts) == 2 else ""
            type_name = (
                analysis.type
                if analysis.type and analysis.type != "unknown"
                else (parts[1] if len(parts) == 2 else cat_label)
            )
            display_type = f"{cat_emoji} {type_name}".strip()

            photo_img = Image.open(BytesIO(image_bytes))
            card_bytes = ItemCardService().render_card(
                photo=photo_img,
                item_type=display_type,
                color=analysis.primary_color or "",
                style=analysis.formality or "",
                season=analysis.season or "",
            )
            await safe_answer_photo(message,
                photo=BufferedInputFile(card_bytes, filename="item_card.jpg"),
                caption=summary,
                reply_markup=confirm_ai_keyboard(),
            )
        except Exception:
            logging.exception("Item card generation failed, sending text fallback")
            await message.answer(summary, reply_markup=confirm_ai_keyboard())
    else:
        # AI не распознал — сразу каскад ручной классификации
        await message.answer(
            "Не удалось распознать вещь автоматически.\n"
            "Давайте укажем вручную. Выберите категорию:",
            reply_markup=manual_category_keyboard(),
        )
        await state.set_state(BotStates.manual_select_category)


@router.callback_query(F.data == "ai_confirm")
async def ai_confirm_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь подтвердил AI-результат."""
    await _safe_answer(callback)
    if not callback.message:
        return

    data = await state.get_data()
    item_id = data.get("ai_saved_item_id")
    await state.update_data(ai_saved_item_id=None)

    await _check_first_outfit_trigger(callback.message, callback.from_user.id)

    # Suggest capsules for the new item
    if item_id:
        await _suggest_capsules_for_item(callback.message, callback.from_user.id, item_id)
    else:
        await callback.message.answer("Что дальше?", reply_markup=after_upload_keyboard())


@router.callback_query(F.data == "ai_manual")
async def ai_manual_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь хочет указать вручную — удаляем AI-запись и запускаем каскад."""
    await _safe_answer(callback)
    if not callback.message:
        return

    data = await state.get_data()
    ai_item_id = data.get("ai_saved_item_id")
    if ai_item_id:
        await delete_item_by_id(user_id=callback.from_user.id, item_id=int(ai_item_id))
        await state.update_data(ai_saved_item_id=None)

    await callback.message.answer(
        "Выберите категорию вещи:",
        reply_markup=manual_category_keyboard(),
    )
    await state.set_state(BotStates.manual_select_category)


# ── Каскад ручной классификации ──────────────────────────────────


@router.callback_query(F.data.startswith("mcat:"))
async def manual_category_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Шаг 1: выбрана категория → показать подкатегории."""
    await _safe_answer(callback)
    if not callback.data or not callback.message:
        return

    category = callback.data.split(":", 1)[1]
    await state.update_data(manual_category=category)
    await state.set_state(BotStates.manual_select_subcategory)
    await callback.message.answer(
        "Выберите тип вещи:",
        reply_markup=subcategory_keyboard(category),
    )


@router.callback_query(F.data.startswith("msub:"))
async def manual_subcategory_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Шаг 2: выбрана подкатегория → показать цвета."""
    await _safe_answer(callback)
    if not callback.data or not callback.message:
        return

    subcategory = callback.data.split(":", 1)[1]
    await state.update_data(manual_subcategory=subcategory)
    await state.set_state(BotStates.manual_select_color)
    await callback.message.answer(
        "Выберите основной цвет:",
        reply_markup=color_keyboard(),
    )


@router.callback_query(F.data.startswith("mcol:"))
async def manual_color_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Шаг 3: выбран цвет → показать сезоны."""
    await _safe_answer(callback)
    if not callback.data or not callback.message:
        return

    color = callback.data.split(":", 1)[1]
    await state.update_data(manual_color=color)
    await state.set_state(BotStates.manual_select_season)
    await callback.message.answer(
        "Выберите сезон:",
        reply_markup=season_inline_keyboard(),
    )


@router.callback_query(F.data.startswith("msea:"))
async def manual_season_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Шаг 4: выбран сезон → показать стили."""
    await _safe_answer(callback)
    if not callback.data or not callback.message:
        return

    season = callback.data.split(":", 1)[1]
    await state.update_data(manual_season=season)
    await state.set_state(BotStates.manual_select_formality)
    await callback.message.answer(
        "Выберите стиль:",
        reply_markup=formality_keyboard(),
    )


@router.callback_query(F.data.startswith("mfor:"))
async def manual_formality_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Шаг 5: выбран стиль → спросить цену."""
    await _safe_answer(callback)
    if not callback.data or not callback.message:
        return

    formality = callback.data.split(":", 1)[1]
    if formality == "skip":
        formality = None
    await state.update_data(manual_formality=formality)
    await state.set_state(BotStates.manual_enter_price)
    await callback.message.answer(
        "Укажите цену вещи в рублях (только число) или отправьте 0, если не хотите указывать:"
    )


@router.message(BotStates.manual_enter_price, F.text)
async def manual_price_entered(message: Message, state: FSMContext) -> None:
    """Шаг 6: введена цена → сохранить вещь."""
    price_text = (message.text or "").strip().replace(" ", "").replace("₽", "").replace("р", "")
    try:
        price = max(0, int(price_text))
    except ValueError:
        await message.answer("Введите число. Например: 2500")
        return

    data = await state.get_data()
    file_id = data.get("manual_file_id")
    category = data.get("manual_category") or data.get("manual_ai_category") or "top"
    subcategory = data.get("manual_subcategory")
    color = data.get("manual_color")
    season = data.get("manual_season")
    formality = data.get("manual_formality")

    if not file_id:
        await message.answer("Ошибка: фото не найдено. Попробуйте загрузить заново.", reply_markup=menu_keyboard())
        await state.set_state(BotStates.menu)
        return

    item_id = await add_item(
        user_id=message.from_user.id,
        category=category,
        telegram_file_id=file_id,
        item_type=subcategory,
        primary_color=color,
        season=season,
        formality=formality,
        display_name=f"{color} {subcategory}" if color and subcategory else subcategory,
        price=price,
    )

    cat_label = CATEGORY_LABELS_RU.get(category, category)
    lines = [
        "✅ Вещь сохранена!",
        f"Категория: {cat_label}",
    ]
    if subcategory:
        lines.append(f"Тип: {subcategory}")
    if color:
        lines.append(f"Цвет: {color}")
    if season:
        lines.append(f"Сезон: {season}")
    if formality:
        lines.append(f"Стиль: {formality}")
    if price > 0:
        lines.append(f"Цена: {price:,} ₽".replace(",", " "))

    await message.answer("\n".join(lines))

    # Очищаем manual state
    await state.update_data(
        manual_file_id=None, manual_category=None, manual_subcategory=None,
        manual_color=None, manual_season=None, manual_formality=None,
        manual_ai_category=None, ai_saved_item_id=None,
    )

    await _check_first_outfit_trigger(message, message.from_user.id)

    await state.set_state(BotStates.upload_photos)
    await message.answer("Что дальше?", reply_markup=after_upload_keyboard())


# ── Кнопки «Меню» в каскаде ─────────────────────────────────────


@router.callback_query(F.data == "mback:category")
async def manual_back_to_category(callback: CallbackQuery, state: FSMContext) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    await state.set_state(BotStates.manual_select_category)
    await callback.message.answer("Выберите категорию:", reply_markup=manual_category_keyboard())


@router.callback_query(F.data == "mback:subcategory")
async def manual_back_to_subcategory(callback: CallbackQuery, state: FSMContext) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    data = await state.get_data()
    category = data.get("manual_category", "top")
    await state.set_state(BotStates.manual_select_subcategory)
    await callback.message.answer("Выберите тип вещи:", reply_markup=subcategory_keyboard(category))


@router.callback_query(F.data == "mback:color")
async def manual_back_to_color(callback: CallbackQuery, state: FSMContext) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    await state.set_state(BotStates.manual_select_color)
    await callback.message.answer("Выберите основной цвет:", reply_markup=color_keyboard())


@router.callback_query(F.data == "mback:season")
async def manual_back_to_season(callback: CallbackQuery, state: FSMContext) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    await state.set_state(BotStates.manual_select_season)
    await callback.message.answer("Выберите сезон:", reply_markup=season_inline_keyboard())


@router.message(BotStates.upload_photos, F.text == "🏠 Меню")
async def back_to_menu_from_upload(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.menu)
    await message.answer("Главное меню:", reply_markup=menu_keyboard())


@router.message(BotStates.upload_photos)
async def upload_photo_prompt(message: Message) -> None:
    await message.answer("Нужно отправить фото.")


@router.message(F.text.in_({"👗 Мой гардероб", "🧺 Мой гардероб", "🧺 Гардероб"}))
async def wardrobe_list(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.wardrobe_view)
    await _render_wardrobe_overview(message=message, user_id=message.from_user.id)


@router.callback_query(F.data.startswith("item:delete:"))
async def ask_delete_wardrobe_item(callback: CallbackQuery) -> None:
    await _safe_answer(callback)
    if not callback.data or not callback.message:
        return

    item_id = int(callback.data.rsplit(":", maxsplit=1)[-1])
    await callback.message.answer(
        "Удалить эту вещь из гардероба?",
        reply_markup=_confirm_delete_keyboard(item_id),
    )


@router.callback_query(F.data.startswith("item:delete_confirm:"))
async def delete_wardrobe_item(callback: CallbackQuery, state: FSMContext) -> None:
    await _safe_answer(callback)
    if not callback.data or not callback.message:
        return

    item_id = int(callback.data.rsplit(":", maxsplit=1)[-1])
    removed = await delete_item_by_id(user_id=callback.from_user.id, item_id=item_id)
    if not removed:
        await callback.message.answer("Не нашла эту вещь. Обновите гардероб и попробуйте снова.")
        return
    await callback.message.answer("Удалила вещь из гардероба.")
    try:
        from services.s3_storage_service import s3_service
        if s3_service.enabled:
            s3_service.delete_photo(callback.from_user.id, item_id)
    except Exception:
        logging.exception("S3 delete failed")
    items_left = await get_items(callback.from_user.id)
    if not items_left:
        await state.set_state(BotStates.menu)
        await callback.message.answer("Гардероб теперь пуст.", reply_markup=menu_keyboard())
        return

    await _render_wardrobe_overview(callback.message, callback.from_user.id)


@router.callback_query(F.data.startswith("item:delete_cancel:"))
async def cancel_delete_wardrobe_item(callback: CallbackQuery) -> None:
    await _safe_answer(callback, "Ок")


@router.callback_query(F.data.startswith("item:rename:"))
async def request_rename_wardrobe_item(callback: CallbackQuery, state: FSMContext) -> None:
    await _safe_answer(callback)
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
    await _safe_answer(callback, "Обрабатываю фото…")
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

    sent = await safe_answer_photo(callback.message,
        photo=BufferedInputFile(processed_image, filename=f"item_{item_id}_enhanced.jpg"),
        caption="Готово! Сохранила улучшенную версию фото.",
    )
    if sent.photo:
        await update_processed_file_id(
            user_id=callback.from_user.id,
            item_id=item_id,
            file_id=sent.photo[-1].file_id,
        )


@router.callback_query(F.data.startswith("set_price:"))
async def request_set_price(callback: CallbackQuery, state: FSMContext) -> None:
    await _safe_answer(callback)
    if not callback.data or not callback.message:
        return

    item_id = int(callback.data.split(":", 1)[1])
    await state.set_state(BotStates.editing_price)
    await state.update_data(editing_price_item_id=item_id)
    await callback.message.answer(
        "Введите цену вещи в рублях (только число):",
        reply_markup=ForceReply(selective=True),
    )


@router.message(BotStates.editing_price, F.text)
async def handle_price_input(message: Message, state: FSMContext) -> None:
    price_text = (message.text or "").strip().replace(" ", "").replace("₽", "").replace("р", "")
    try:
        price = max(0, int(price_text))
    except ValueError:
        await message.answer("Введите число. Например: 2500")
        return

    data = await state.get_data()
    item_id = data.get("editing_price_item_id")
    if not item_id:
        await message.answer("Ошибка. Попробуйте ещё раз через карточку вещи.")
        await state.set_state(BotStates.wardrobe_view)
        return

    updated = await update_item_price(
        user_id=message.from_user.id,
        item_id=int(item_id),
        price=price,
    )
    await state.update_data(editing_price_item_id=None)
    await state.set_state(BotStates.wardrobe_view)

    if updated:
        await message.answer(f"Цена обновлена: {price:,} ₽".replace(",", " "))
    else:
        await message.answer("Не удалось обновить цену. Попробуйте снова.")


@router.message(BotStates.wardrobe_view, F.text == "🏠 Меню")
async def wardrobe_back_to_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.menu)
    await state.update_data(rename_item_id=None)
    await message.answer("Главное меню:", reply_markup=menu_keyboard())


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
    await _render_wardrobe_overview(message, message.from_user.id)


# ── Контекстные action-кнопки ────────────────────────────────────


@router.callback_query(F.data == "action:upload")
async def action_upload(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    if not callback.message:
        return
    await state.set_state(BotStates.upload_category)
    await callback.message.answer("Выберите категорию:", reply_markup=category_keyboard())


@router.callback_query(F.data == "action:wardrobe")
async def action_wardrobe(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    if not callback.message:
        return
    await state.set_state(BotStates.wardrobe_view)
    await _render_wardrobe_overview(message=callback.message, user_id=callback.from_user.id)


# ── Task 12: быстрый первый образ ───────────────────────────────


@router.callback_query(F.data == "outfit:quick_first")
async def quick_first_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    """Собрать образ из того, что есть (даже 2 вещи без обуви)."""
    await _safe_answer(callback)
    if not callback.message:
        return
    items = await get_items(callback.from_user.id)
    if len(items) < 2:
        await callback.message.answer("Добавь хотя бы 2 вещи для первого образа.")
        return

    from services.weather_service import detect_season_for_user
    season, weather_msg = await detect_season_for_user(callback.from_user.id)
    await callback.message.answer(weather_msg)

    # Импортируем _generate_and_show_outfit из outfits router
    from bot.routers.outfits import _generate_and_show_outfit
    await _generate_and_show_outfit(
        message=callback.message,
        state=state,
        occasion_code="casual",
        season=season,
    )


@router.callback_query(F.data == "continue_upload")
async def continue_upload_handler(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь хочет добавить ещё вещи перед первым образом."""
    await _safe_answer(callback)
    if not callback.message:
        return
    await state.set_state(BotStates.upload_photos)
    await callback.message.answer(
        "Хорошо! Добавь следующую вещь.",
        reply_markup=photo_upload_keyboard(),
    )


# ── Гардероб: навигация по категориям и пагинация ────────────────


@router.callback_query(F.data.startswith("wardrobe:cat:"))
async def wardrobe_category(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    if not callback.message:
        return
    category = callback.data.split(":", 2)[2]
    await _render_wardrobe_page(callback.message, callback.from_user.id, category, page=0)


@router.callback_query(F.data == "wardrobe:all")
async def wardrobe_all(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    if not callback.message:
        return
    await _render_wardrobe_page(callback.message, callback.from_user.id, category=None, page=0)


@router.callback_query(F.data.startswith("wardrobe:page:"))
async def wardrobe_page(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    if not callback.message:
        return
    parts = callback.data.split(":")
    # wardrobe:page:<cat_or_all>:<page>
    cat_part = parts[2]
    page = int(parts[3])
    category = None if cat_part == "all" else cat_part
    await _render_wardrobe_page(callback.message, callback.from_user.id, category, page)


@router.callback_query(F.data == "wardrobe:back")
async def wardrobe_back(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    if not callback.message:
        return
    await _render_wardrobe_overview(callback.message, callback.from_user.id)


@router.callback_query(F.data.startswith("wardrobe:item:"))
async def wardrobe_item_detail(callback: CallbackQuery) -> None:
    try:
        await callback.answer()
    except Exception:
        pass
    if not callback.message:
        return
    item_id = int(callback.data.split(":", 2)[2])
    user_id = callback.from_user.id
    items = await get_items(user_id)
    item = next((i for i in items if int(i["id"]) == item_id), None)
    if not item:
        await callback.message.answer("Вещь не найдена.")
        return

    caption = _build_item_caption(item)
    preview_file_id = item.get("processed_file_id") or item.get("telegram_file_id")
    if preview_file_id:
        await safe_answer_photo(callback.message,
            photo=str(preview_file_id),
            caption=caption,
            reply_markup=_item_detail_keyboard(item_id),
        )
    else:
        await callback.message.answer(
            f"📸 Фото недоступно\n{caption}",
            reply_markup=_item_detail_keyboard(item_id),
        )


# ── Task 13: фильтрация и сортировка гардероба ──────────────────


async def _show_items_page(message: Message, items: list[dict], label: str, page: int = 0) -> None:
    """Показать страницу из 5 вещей (текстовые карточки)."""
    page_size = 5
    start = page * page_size
    page_items = items[start:start + page_size]
    total = len(items)

    header = f"{label}: {total} вещ{'ь' if total == 1 else 'и' if 2 <= total <= 4 else 'ей'}"
    await message.answer(header)

    for item in page_items:
        preview_file_id = item.get("processed_file_id") or item.get("telegram_file_id")
        caption = _build_item_caption(item)
        price = item.get("price") or 0
        if price:
            caption += f"\n💰 {_format_price(price)}"
        if preview_file_id:
            await safe_answer_photo(message,
                photo=str(preview_file_id),
                caption=caption,
                reply_markup=_item_actions_keyboard(int(item["id"])),
            )
        else:
            await message.answer(caption, reply_markup=_item_actions_keyboard(int(item["id"])))

    # Показать ещё
    if start + page_size < total:
        remaining = total - start - page_size
        await message.answer(
            f"Показано {min(page_size, total)} из {total}. Ещё {remaining} вещей.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"Показать ещё ({remaining})", callback_data=f"wpage:{page+1}:{label}")]
            ]),
        )


@router.callback_query(F.data.startswith("wfilter:"))
async def wardrobe_filter(callback: CallbackQuery) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    user_id = callback.from_user.id
    items = await get_items(user_id)

    filter_key = callback.data.split(":", 1)[1]

    if filter_key == "all":
        filtered = items
        label = "📋 Все вещи"
    elif filter_key.startswith("s:"):
        season = filter_key.split(":")[1]
        filtered = [i for i in items if (i.get("season") or "").lower() == season]
        label = {"winter": "❄️ Зимние", "demi": "🍂 Демисезон", "summer": "☀️ Летние"}.get(season, season)
    else:
        filtered = [i for i in items if i.get("category") == filter_key]
        label = CATEGORY_LABELS_RU.get(filter_key, filter_key)

    if not filtered:
        await callback.message.answer(f"{label}: пусто")
        return

    await _show_items_page(callback.message, filtered, label, page=0)


@router.callback_query(F.data.startswith("wsort:"))
async def wardrobe_sort(callback: CallbackQuery) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    items = await get_items(callback.from_user.id)

    sort_key = callback.data.split(":")[1]
    if sort_key == "price_desc":
        items = sorted(items, key=lambda x: x.get("price") or 0, reverse=True)
        label = "💰 По цене (дорогие → дешёвые)"
    elif sort_key == "date_desc":
        items = sorted(items, key=lambda x: x.get("created_at") or "", reverse=True)
        label = "🕐 Новые первые"
    else:
        label = "📋 Все вещи"

    await _show_items_page(callback.message, items, label, page=0)


# ── /check — проверка совместимости двух вещей ──────────────────


@router.message(Command("check"))
async def cmd_check(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.check_compatibility)
    await state.update_data(check_photo_1=None)
    await message.answer(
        "Пришли фото первой вещи, и я скажу, сочетается ли она со второй.",
        reply_markup=photo_upload_keyboard(),
    )


@router.message(BotStates.check_compatibility, F.photo)
async def handle_check_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    file_id = message.photo[-1].file_id

    if not data.get("check_photo_1"):
        await state.update_data(check_photo_1=file_id)
        await message.answer("Отлично! Теперь пришли фото второй вещи.")
        return

    photo1_id = data["check_photo_1"]
    await state.update_data(check_photo_1=None)
    await state.set_state(BotStates.menu)

    await message.answer("Анализирую совместимость… ⏳")

    try:
        from io import BytesIO
        import base64
        import httpx
        from config.settings import settings

        async def _download_b64(fid: str) -> str:
            tg_file = await message.bot.get_file(fid)
            buf = BytesIO()
            await message.bot.download(tg_file, destination=buf)
            return base64.b64encode(buf.getvalue()).decode()

        b64_1, b64_2 = await _download_b64(photo1_id), await _download_b64(file_id)

        content = [
            {"type": "text", "text": (
                "Ты — стилист. Посмотри на две вещи и скажи, сочетаются ли они между собой.\n"
                "Ответь коротко: 1) Да/Нет/Частично, 2) Почему, 3) Совет по образу.\n"
                "Пиши на русском, без markdown."
            )},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_1}"}},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_2}"}},
        ]

        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post(
                f"{settings.ai_api_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.ai_api_key}", "Content-Type": "application/json"},
                json={"model": settings.ai_model, "messages": [{"role": "user", "content": content}], "max_tokens": 300},
            )
            resp.raise_for_status()
            answer = resp.json()["choices"][0]["message"]["content"].strip()

        await message.answer(f"🎨 Результат:\n\n{answer}", reply_markup=menu_keyboard())
    except Exception:
        logging.exception("Check compatibility failed")
        await message.answer(
            "Не удалось проверить совместимость. Попробуйте позже.",
            reply_markup=menu_keyboard(),
        )


@router.message(BotStates.check_compatibility, F.text == "🏠 Меню")
async def check_back(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.menu)
    await message.answer("Главное меню:", reply_markup=menu_keyboard())


# ── Task 15: советы стилиста ─────────────────────────────────────


@router.message(Command("advice"))
async def cmd_style_advice(message: Message) -> None:
    from services.subscription_service import get_or_create_user
    user = await get_or_create_user(message.from_user.id)
    is_premium = user.get("subscription_status") == "active"

    if not is_premium:
        await message.answer(
            "💡 Персональные советы стилиста — функция подписки.\n\n"
            "Я проанализирую весь твой гардероб и дам 3 совета: "
            "по цветам, стилю и сезонности.\n\n"
            f"💎 Подписка — {settings.subscription_price} ₽/мес",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 Оформить", callback_data="pay:subscribe")],
            ]),
        )
        return

    items = await get_items(message.from_user.id)
    if len(items) < 5:
        await message.answer("Добавь хотя бы 5 вещей, чтобы я мог дать точные советы.")
        return

    await message.answer("💡 Анализирую твой гардероб…")

    from services.style_advisor_service import generate_personal_advice
    advice = await generate_personal_advice(items)
    if advice:
        await message.answer(f"💡 Советы стилиста:\n\n{advice}")
    else:
        await message.answer("Не удалось подготовить советы. Попробуй позже.")


# ── Капсулы гардероба ──────────────────────────────────────────


@router.message(F.text == "💊 Капсулы")
async def capsules_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.menu)
    capsules = await get_user_capsules(message.from_user.id)
    if not capsules:
        await message.answer(
            "💊 У тебя пока нет капсул.\n\n"
            "Капсула — это набор вещей, объединённых стилем или поводом "
            "(например, «Офис» или «Кэжуал»).\n\n"
            "Нажми «🪄 Авто-создание», чтобы я проанализировал гардероб "
            "и создал капсулы автоматически.",
            reply_markup=capsule_list_keyboard([]),
        )
        return
    await message.answer("💊 Твои капсулы:", reply_markup=capsule_list_keyboard(capsules))


@router.callback_query(F.data == "capsule:list")
async def capsule_list_handler(callback: CallbackQuery) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    capsules = await get_user_capsules(callback.from_user.id)
    await callback.message.answer("💊 Твои капсулы:", reply_markup=capsule_list_keyboard(capsules))


@router.callback_query(F.data == "capsule:auto")
async def capsule_auto_create(callback: CallbackQuery) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    from services.capsule_service import auto_create_capsules
    created = await auto_create_capsules(callback.from_user.id)
    if not created:
        await callback.message.answer(
            "Не удалось создать капсулы автоматически.\n"
            "Добавь больше вещей с разным стилем (офисный, повседневный, спортивный)."
        )
        return
    lines = ["🪄 Созданы капсулы:\n"]
    for c in created:
        lines.append(f"{c['icon']} {c['name']} — {c['count']} вещей")
    await callback.message.answer("\n".join(lines))
    capsules = await get_user_capsules(callback.from_user.id)
    await callback.message.answer("💊 Твои капсулы:", reply_markup=capsule_list_keyboard(capsules))


@router.callback_query(F.data == "capsule:create")
async def capsule_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    await state.set_state(BotStates.capsule_create_name)
    await callback.message.answer("Введи название новой капсулы (например, «Отпуск» или «Работа»):")


@router.message(BotStates.capsule_create_name, F.text)
async def capsule_create_name_handler(message: Message, state: FSMContext) -> None:
    if message.text == "🏠 Меню":
        await state.set_state(BotStates.menu)
        await message.answer("Главное меню:", reply_markup=menu_keyboard())
        return
    name = message.text.strip()[:50]
    if not name:
        await message.answer("Название не может быть пустым. Попробуй ещё:")
        return
    from bot.storage import create_capsule
    capsule_id = await create_capsule(message.from_user.id, name)
    await state.set_state(BotStates.menu)
    await message.answer(f"Капсула «{name}» создана!")
    capsules = await get_user_capsules(message.from_user.id)
    await message.answer("💊 Твои капсулы:", reply_markup=capsule_list_keyboard(capsules))


@router.callback_query(F.data.startswith("capsule:view:"))
async def capsule_view(callback: CallbackQuery) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    capsule_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id
    capsule = await get_capsule_by_id(user_id, capsule_id)
    if not capsule:
        await callback.message.answer("Капсула не найдена.")
        return
    items = await get_capsule_items(user_id, capsule_id)
    icon = capsule.get("icon") or "👗"
    name = capsule.get("name") or "Капсула"
    if not items:
        await callback.message.answer(
            f"{icon} {name}\n\nКапсула пока пуста. Добавь вещи!",
            reply_markup=capsule_detail_keyboard(capsule_id),
        )
        return
    lines = [f"{icon} {name} ({len(items)} вещей)\n"]
    for i, item in enumerate(items, 1):
        title = _item_title(item)
        cat = _CAT_SHORT.get(item.get("category", ""), "")
        lines.append(f"{i}. {cat} — {title}")
    await callback.message.answer(
        "\n".join(lines),
        reply_markup=capsule_detail_keyboard(capsule_id),
    )


@router.callback_query(F.data.startswith("capsule:delete:"))
async def capsule_delete_handler(callback: CallbackQuery) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    capsule_id = int(callback.data.split(":")[2])
    deleted = await delete_capsule(callback.from_user.id, capsule_id)
    if deleted:
        await callback.message.answer("Капсула удалена.")
    else:
        await callback.message.answer("Не удалось удалить капсулу.")
    capsules = await get_user_capsules(callback.from_user.id)
    await callback.message.answer("💊 Твои капсулы:", reply_markup=capsule_list_keyboard(capsules))


@router.callback_query(F.data.startswith("capsule:add:"))
async def capsule_add_item_start(callback: CallbackQuery) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    capsule_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id

    # Get items NOT already in this capsule
    all_items = await get_items(user_id)
    capsule_items = await get_capsule_items(user_id, capsule_id)
    capsule_item_ids = {it["id"] for it in capsule_items}
    available = [it for it in all_items if it["id"] not in capsule_item_ids]

    if not available:
        await callback.message.answer("Все вещи уже в этой капсуле!")
        return

    await callback.message.answer(
        "Выбери вещь для добавления:",
        reply_markup=capsule_add_item_keyboard(capsule_id, available),
    )


@router.callback_query(F.data.startswith("capsule:additem:"))
async def capsule_add_item_handler(callback: CallbackQuery) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    parts = callback.data.split(":")
    capsule_id = int(parts[2])
    item_id = int(parts[3])
    added = await add_item_to_capsule(capsule_id, item_id)
    if added:
        await callback.message.answer("Вещь добавлена в капсулу!")
    else:
        await callback.message.answer("Вещь уже в этой капсуле.")
    # Show capsule again
    capsule = await get_capsule_by_id(callback.from_user.id, capsule_id)
    if capsule:
        items = await get_capsule_items(callback.from_user.id, capsule_id)
        icon = capsule.get("icon") or "👗"
        name = capsule.get("name") or "Капсула"
        lines = [f"{icon} {name} ({len(items)} вещей)\n"]
        for i, item in enumerate(items, 1):
            title = _item_title(item)
            cat = _CAT_SHORT.get(item.get("category", ""), "")
            lines.append(f"{i}. {cat} — {title}")
        await callback.message.answer(
            "\n".join(lines),
            reply_markup=capsule_detail_keyboard(capsule_id),
        )


@router.callback_query(F.data.startswith("capsule:rmitem:"))
async def capsule_remove_item_handler(callback: CallbackQuery) -> None:
    await _safe_answer(callback)
    if not callback.message:
        return
    parts = callback.data.split(":")
    capsule_id = int(parts[2])
    item_id = int(parts[3])
    await remove_item_from_capsule(capsule_id, item_id)
    await callback.message.answer("Вещь убрана из капсулы.")
    # Redirect back to capsule view
    capsule = await get_capsule_by_id(callback.from_user.id, capsule_id)
    if capsule:
        items = await get_capsule_items(callback.from_user.id, capsule_id)
        icon = capsule.get("icon") or "👗"
        name = capsule.get("name") or "Капсула"
        lines = [f"{icon} {name} ({len(items)} вещей)\n"]
        for i, item in enumerate(items, 1):
            title = _item_title(item)
            cat = _CAT_SHORT.get(item.get("category", ""), "")
            lines.append(f"{i}. {cat} — {title}")
        await callback.message.answer(
            "\n".join(lines),
            reply_markup=capsule_detail_keyboard(capsule_id),
        )


@router.callback_query(F.data.startswith("capsule:outfit:"))
async def capsule_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    """Generate outfit from a specific capsule."""
    await _safe_answer(callback)
    if not callback.message:
        return
    capsule_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id
    items = await get_capsule_items(user_id, capsule_id)
    if len(items) < 2:
        await callback.message.answer("В капсуле слишком мало вещей для образа. Добавь ещё!")
        return
    # Store capsule items in state so outfit generation uses them
    await state.update_data(capsule_items_ids=[it["id"] for it in items])
    from bot.keyboards import occasion_keyboard
    await state.set_state(BotStates.request_occasion)
    await callback.message.answer(
        "Куда ты сегодня идёшь?\nСоберу образ из этой капсулы.",
        reply_markup=occasion_keyboard(),
    )


@router.callback_query(F.data.startswith("capsule:gen:"))
async def capsule_gen_outfit(callback: CallbackQuery, state: FSMContext) -> None:
    """Generate outfit from capsule after occasion was already chosen."""
    await _safe_answer(callback)
    if not callback.message:
        return
    parts = callback.data.split(":")
    capsule_part = parts[2]  # capsule_id or "all"
    occasion = parts[3] if len(parts) > 3 else "casual"

    if capsule_part != "all":
        capsule_id = int(capsule_part)
        user_id = callback.from_user.id
        items = await get_capsule_items(user_id, capsule_id)
        if len(items) < 2:
            await callback.message.answer("В капсуле слишком мало вещей для образа.")
            return
        await state.update_data(capsule_items_ids=[it["id"] for it in items])
    else:
        await state.update_data(capsule_items_ids=None)

    from bot.routers.outfits import _show_base_selection
    await _show_base_selection(callback.message, state, occasion)


@router.callback_query(F.data.startswith("capsule:suggest:"))
async def capsule_suggest_handler(callback: CallbackQuery) -> None:
    """Handle post-upload capsule suggestion."""
    await _safe_answer(callback)
    if not callback.message:
        return
    parts = callback.data.split(":")
    if parts[2] == "skip":
        await callback.message.answer("Что дальше?", reply_markup=after_upload_keyboard())
        return
    item_id = int(parts[2])
    capsule_name = parts[3] if len(parts) > 3 else ""

    # Find capsule by name
    capsules = await get_user_capsules(callback.from_user.id)
    capsule = next((c for c in capsules if c["name"] == capsule_name), None)
    if capsule:
        added = await add_item_to_capsule(capsule["id"], item_id)
        if added:
            await callback.message.answer(f"Добавлено в капсулу «{capsule_name}»!")
        else:
            await callback.message.answer("Вещь уже в этой капсуле.")
    await callback.message.answer("Что дальше?", reply_markup=after_upload_keyboard())

