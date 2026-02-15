from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📥 Загрузить"),
                KeyboardButton(text="✨ Образы"),
            ],
            [
                KeyboardButton(text="🧺 Гардероб"),
                KeyboardButton(text="💳 Подписка"),
            ],
            [
                KeyboardButton(text="🎨 Модные тренды"),
                KeyboardButton(text="📝 Обратная связь"),
            ],
        ],
        resize_keyboard=True,
    )


def occasion_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏢 Работа/офис")],
            [KeyboardButton(text="✨ Выход в люди")],
            [KeyboardButton(text="🎒 Спорт/прогулки")],
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
