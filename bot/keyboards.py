from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔥 Сегодня"),
                KeyboardButton(text="✨ Собрать образ"),
            ],
            [
                KeyboardButton(text="📥 Добавить вещь"),
                KeyboardButton(text="🧺 Мой гардероб"),
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
