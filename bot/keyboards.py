from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from config.categories import (
    CATEGORY_LABELS_RU, SUBCATEGORIES,
    COLORS_RU, SEASONS_RU, FORMALITY_RU,
)


def menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✨ Собрать образ")],
            [KeyboardButton(text="📸 Добавить вещь")],
            [KeyboardButton(text="⚙️ Ещё")],
        ],
        resize_keyboard=True,
    )


def more_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👗 Мой гардероб"), KeyboardButton(text="💊 Капсулы")],
            [KeyboardButton(text="🔥 Тренды"), KeyboardButton(text="💎 Подписка")],
            [KeyboardButton(text="🏠 Меню")],
        ],
        resize_keyboard=True,
    )


def occasion_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏢 Работа/офис"), KeyboardButton(text="💼 Собеседование")],
            [KeyboardButton(text="💕 Свидание"), KeyboardButton(text="🎉 Вечеринка")],
            [KeyboardButton(text="🚶 Прогулка"), KeyboardButton(text="🏃 Спорт")],
            [KeyboardButton(text="🏠 Меню")],
        ],
        resize_keyboard=True,
    )


def season_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❄️ Зима")],
            [KeyboardButton(text="🍂 Весна/осень")],
            [KeyboardButton(text="☀️ Лето")],
            [KeyboardButton(text="🏠 Меню")],
        ],
        resize_keyboard=True,
    )


def category_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👕 Верх"), KeyboardButton(text="👖 Низ")],
            [KeyboardButton(text="🧥 Верхняя одежда"), KeyboardButton(text="👟 Обувь")],
            [KeyboardButton(text="🧢 Аксессуары"), KeyboardButton(text="👔 Цельный образ")],
            [KeyboardButton(text="🏠 Меню")],
        ],
        resize_keyboard=True,
    )


def photo_upload_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏠 Меню")]],
        resize_keyboard=True,
    )


def wardrobe_view_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏠 Меню")]],
        resize_keyboard=True,
    )


def outfit_reaction_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👍 Нравится", callback_data="outfit:like"),
                InlineKeyboardButton(text="🔄 Другой вариант", callback_data="outfit:reroll"),
            ],
            [
                InlineKeyboardButton(text="🧠 Почему так?", callback_data="outfit:why"),
                InlineKeyboardButton(text="✨ Визуализация", callback_data="outfit:visualize"),
            ],
        ]
    )


def manual_category_keyboard() -> InlineKeyboardMarkup:
    """7 категорий, по 2 в ряд."""
    buttons = []
    items = list(CATEGORY_LABELS_RU.items())
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(text=label, callback_data=f"mcat:{key}")
               for key, label in items[i:i+2]]
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def subcategory_keyboard(category: str) -> InlineKeyboardMarkup:
    """Подкатегории для категории, по 2 в ряд."""
    subs = SUBCATEGORIES.get(category, [])
    buttons = []
    for i in range(0, len(subs), 2):
        row = [InlineKeyboardButton(text=sub, callback_data=f"msub:{sub}")
               for sub in subs[i:i+2]]
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="action:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def color_keyboard() -> InlineKeyboardMarkup:
    """20 цветов, по 3 в ряд."""
    buttons = []
    for i in range(0, len(COLORS_RU), 3):
        row = [InlineKeyboardButton(text=c, callback_data=f"mcol:{c}")
               for c in COLORS_RU[i:i+3]]
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="action:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def season_inline_keyboard() -> InlineKeyboardMarkup:
    """4 сезона."""
    buttons = [[InlineKeyboardButton(text=label, callback_data=f"msea:{code}")]
               for label, code in SEASONS_RU.items()]
    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="action:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def formality_keyboard() -> InlineKeyboardMarkup:
    """4 стиля + пропустить."""
    buttons = [[InlineKeyboardButton(text=label, callback_data=f"mfor:{code}")]
               for label, code in FORMALITY_RU.items()]
    buttons.append([InlineKeyboardButton(text="⏩ Пропустить", callback_data="mfor:skip")])
    buttons.append([InlineKeyboardButton(text="🏠 Меню", callback_data="action:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_ai_keyboard() -> InlineKeyboardMarkup:
    """После AI-распознавания: подтвердить или указать вручную."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Всё верно", callback_data="ai_confirm"),
            InlineKeyboardButton(text="✏️ Указать вручную", callback_data="ai_manual"),
        ]
    ])


def wardrobe_filter_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👕 Верх", callback_data="wfilter:top"),
            InlineKeyboardButton(text="👖 Низ", callback_data="wfilter:bottom"),
            InlineKeyboardButton(text="👟 Обувь", callback_data="wfilter:shoes"),
        ],
        [
            InlineKeyboardButton(text="🧥 Верхняя", callback_data="wfilter:outerwear"),
            InlineKeyboardButton(text="👗 Платья", callback_data="wfilter:onepiece"),
            InlineKeyboardButton(text="🎩 Аксессуары", callback_data="wfilter:accessory"),
        ],
        [
            InlineKeyboardButton(text="❄️ Зима", callback_data="wfilter:s:winter"),
            InlineKeyboardButton(text="🍂 Демисезон", callback_data="wfilter:s:demi"),
            InlineKeyboardButton(text="☀️ Лето", callback_data="wfilter:s:summer"),
        ],
        [
            InlineKeyboardButton(text="💰 По цене ↓", callback_data="wsort:price_desc"),
            InlineKeyboardButton(text="🕐 Новые", callback_data="wsort:date_desc"),
        ],
        [
            InlineKeyboardButton(text="📋 Все вещи", callback_data="wfilter:all"),
        ],
    ])


def after_upload_keyboard() -> InlineKeyboardMarkup:
    """После подтверждения загрузки вещи: добавить ещё / образ / гардероб."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📸 Добавить ещё", callback_data="action:upload"),
            InlineKeyboardButton(text="✨ Собрать образ", callback_data="action:outfit"),
        ],
        [
            InlineKeyboardButton(text="👗 Мой гардероб", callback_data="action:wardrobe"),
        ],
    ])


def after_like_keyboard() -> InlineKeyboardMarkup:
    """После лайка образа: ещё на тот же повод / другой повод / добавить вещь / меню."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Ещё на этот повод", callback_data="action:reroll_same"),
            InlineKeyboardButton(text="👗 Другой повод", callback_data="action:outfit"),
        ],
        [
            InlineKeyboardButton(text="📸 Добавить вещь", callback_data="action:upload"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="action:menu"),
        ],
    ])


def after_why_keyboard() -> InlineKeyboardMarkup:
    """После объяснения «Почему так»: те же реакции + другой повод + меню."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍 Нравится", callback_data="outfit:like"),
            InlineKeyboardButton(text="🔄 Другой вариант", callback_data="outfit:reroll"),
        ],
        [
            InlineKeyboardButton(text="👗 Другой повод", callback_data="action:outfit"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="action:menu"),
        ],
    ])


def location_request_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой геолокации + текстовый ввод."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Отправить геолокацию", request_location=True)],
            [KeyboardButton(text="⬅️ Пропустить (Москва)")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ── Capsule keyboards ──────────────────────────────────────────


def capsule_list_keyboard(capsules: list[dict]) -> InlineKeyboardMarkup:
    """List of user capsules + management buttons."""
    rows: list[list[InlineKeyboardButton]] = []
    for cap in capsules:
        icon = cap.get("icon") or "👗"
        name = cap.get("name") or "Капсула"
        count = cap.get("item_count", 0)
        rows.append([InlineKeyboardButton(
            text=f"{icon} {name} ({count})",
            callback_data=f"capsule:view:{cap['id']}",
        )])
    rows.append([
        InlineKeyboardButton(text="🪄 Авто-создание", callback_data="capsule:auto"),
        InlineKeyboardButton(text="➕ Создать", callback_data="capsule:create"),
    ])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="action:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def capsule_detail_keyboard(capsule_id: int) -> InlineKeyboardMarkup:
    """Actions for a single capsule."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✨ Образ из капсулы", callback_data=f"capsule:outfit:{capsule_id}"),
        ],
        [
            InlineKeyboardButton(text="➕ Добавить вещь", callback_data=f"capsule:add:{capsule_id}"),
            InlineKeyboardButton(text="🗑 Удалить капсулу", callback_data=f"capsule:delete:{capsule_id}"),
        ],
        [
            InlineKeyboardButton(text="💊 К капсулам", callback_data="capsule:list"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="action:menu"),
        ],
    ])


def capsule_select_keyboard(capsules: list[dict], occasion: str) -> InlineKeyboardMarkup:
    """Select capsule for outfit generation (shown before generating)."""
    rows: list[list[InlineKeyboardButton]] = []
    for cap in capsules:
        icon = cap.get("icon") or "👗"
        name = cap.get("name") or "Капсула"
        rows.append([InlineKeyboardButton(
            text=f"{icon} {name}",
            callback_data=f"capsule:gen:{cap['id']}:{occasion}",
        )])
    rows.append([InlineKeyboardButton(
        text="📋 Весь гардероб",
        callback_data=f"capsule:gen:all:{occasion}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def capsule_add_item_keyboard(capsule_id: int, items: list[dict]) -> InlineKeyboardMarkup:
    """Pick items to add to a capsule (show first 10)."""
    rows: list[list[InlineKeyboardButton]] = []
    for item in items[:10]:
        name = item.get("display_name") or item.get("type") or "вещь"
        rows.append([InlineKeyboardButton(
            text=f"{name}",
            callback_data=f"capsule:additem:{capsule_id}:{item['id']}",
        )])
    rows.append([
        InlineKeyboardButton(text="💊 Назад к капсуле", callback_data=f"capsule:view:{capsule_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def capsule_item_keyboard(capsule_id: int, item_id: int) -> InlineKeyboardMarkup:
    """Remove item from capsule."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Убрать из капсулы", callback_data=f"capsule:rmitem:{capsule_id}:{item_id}")],
        [InlineKeyboardButton(text="💊 Назад к капсуле", callback_data=f"capsule:view:{capsule_id}")],
    ])


def after_upload_capsule_keyboard(capsule_names: list[str], item_id: int) -> InlineKeyboardMarkup:
    """Suggest adding newly uploaded item to capsules."""
    rows: list[list[InlineKeyboardButton]] = []
    for name in capsule_names[:3]:
        rows.append([InlineKeyboardButton(
            text=f"➕ В капсулу «{name}»",
            callback_data=f"capsule:suggest:{item_id}:{name}",
        )])
    rows.append([
        InlineKeyboardButton(text="⏩ Пропустить", callback_data="capsule:suggest:skip"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Base item selection keyboards ──────────────────────────────


_BASE_CAT_EMOJI = {
    "top": "👕", "bottom": "👖", "outerwear": "🧥",
    "shoes": "👟", "accessory": "🧢", "onepiece": "👔",
}


def base_item_select_keyboard(items: list[dict], occasion: str) -> InlineKeyboardMarkup:
    """Select base item for multi-outfit generation."""
    rows: list[list[InlineKeyboardButton]] = []
    for item in items[:8]:
        cat = item.get("category", "")
        emoji = _BASE_CAT_EMOJI.get(cat, "📦")
        name = item.get("display_name") or item.get("type") or "вещь"
        color = item.get("primary_color") or ""
        label = f"{emoji} {color} {name}".strip()[:40]
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"base:item:{item['id']}:{occasion}",
        )])
    rows.append([InlineKeyboardButton(
        text="🎲 Бот выберет сам",
        callback_data=f"base:auto:{occasion}",
    )])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="action:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def outfit_choice_keyboard(count: int) -> InlineKeyboardMarkup:
    """Buttons 1/2/3 + Другая база + Меню."""
    num_row = []
    for i in range(1, count + 1):
        num_row.append(InlineKeyboardButton(text=f"{i}\u20e3", callback_data=f"outfit:pick:{i}"))
    rows = [num_row]
    rows.append([
        InlineKeyboardButton(text="🔄 Другая база", callback_data="outfit:change_base"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="action:menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
