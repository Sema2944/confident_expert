from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📸 Загрузить гардероб")],
            [KeyboardButton(text="👗 Собрать образы")],
            [KeyboardButton(text="🧺 Мой гардероб")],
            [KeyboardButton(text="💳 Подписка")],
        ],
        resize_keyboard=True,
    )


def occasion_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏢 Работа/офис")],
            [KeyboardButton(text="✨ Выход в люди")],
            [KeyboardButton(text="🎒 Спорт/прогулки")],
        ],
        resize_keyboard=True,
    )


def season_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❄️ Зима")],
            [KeyboardButton(text="🍂 Весна/осень")],
            [KeyboardButton(text="☀️ Лето")],
        ],
        resize_keyboard=True,
    )
