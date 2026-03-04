from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from config.categories import (
    CATEGORY_LABELS_RU, SUBCATEGORIES,
    COLORS_RU, SEASONS_RU, FORMALITY_RU,
)


def menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✨ Собрать образ")],
            [KeyboardButton(text="👗 Мой гардероб"), KeyboardButton(text="📥 Добавить вещь")],
            [KeyboardButton(text="🔥 Тренды"), KeyboardButton(text="💎 Подписка")],
        ],
        resize_keyboard=True,
    )


def occasion_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏢 Работа/офис"), KeyboardButton(text="💼 Собеседование")],
            [KeyboardButton(text="💕 Свидание"), KeyboardButton(text="🎉 Вечеринка")],
            [KeyboardButton(text="🚶 Прогулка"), KeyboardButton(text="🏃 Спорт")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def season_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❄️ Зима")],
            [KeyboardButton(text="🍂 Весна/осень")],
            [KeyboardButton(text="☀️ Лето")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def category_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👕 Верх"), KeyboardButton(text="👖 Низ")],
            [KeyboardButton(text="🧥 Верхняя одежда"), KeyboardButton(text="👟 Обувь")],
            [KeyboardButton(text="🧢 Аксессуары"), KeyboardButton(text="👔 Цельный образ")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )


def photo_upload_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True,
    )


def wardrobe_view_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад")]],
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
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="mback:category")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def color_keyboard() -> InlineKeyboardMarkup:
    """20 цветов, по 3 в ряд."""
    buttons = []
    for i in range(0, len(COLORS_RU), 3):
        row = [InlineKeyboardButton(text=c, callback_data=f"mcol:{c}")
               for c in COLORS_RU[i:i+3]]
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="mback:subcategory")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def season_inline_keyboard() -> InlineKeyboardMarkup:
    """4 сезона."""
    buttons = [[InlineKeyboardButton(text=label, callback_data=f"msea:{code}")]
               for label, code in SEASONS_RU.items()]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="mback:color")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def formality_keyboard() -> InlineKeyboardMarkup:
    """4 стиля + пропустить."""
    buttons = [[InlineKeyboardButton(text=label, callback_data=f"mfor:{code}")]
               for label, code in FORMALITY_RU.items()]
    buttons.append([InlineKeyboardButton(text="⏩ Пропустить", callback_data="mfor:skip")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="mback:season")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_ai_keyboard() -> InlineKeyboardMarkup:
    """После AI-распознавания: подтвердить или указать вручную."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Всё верно", callback_data="ai_confirm"),
            InlineKeyboardButton(text="✏️ Указать вручную", callback_data="ai_manual"),
        ]
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
