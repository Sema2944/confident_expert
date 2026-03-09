"""Клавиатуры MAX-бота (inline-кнопки через AttachmentButton)."""

from maxapi.types import CallbackButton, LinkButton
from maxapi.types.attachments.attachment import ButtonsPayload
from maxapi.types.attachments.buttons.attachment_button import AttachmentButton


def _inline_kb(rows: list[list]) -> AttachmentButton:
    """Helper: построить inline-клавиатуру из рядов кнопок."""
    return AttachmentButton(
        type="inline_keyboard",
        payload=ButtonsPayload(buttons=rows),
    )


def menu_keyboard() -> AttachmentButton:
    return _inline_kb([
        [CallbackButton(text="✨ Собрать образ", payload="action:outfit")],
        [
            CallbackButton(text="👗 Мой гардероб", payload="action:wardrobe"),
            CallbackButton(text="📸 Добавить вещь", payload="action:upload"),
        ],
        [
            CallbackButton(text="💎 Подписка", payload="action:subscribe"),
        ],
    ])


def occasion_keyboard() -> AttachmentButton:
    return _inline_kb([
        [
            CallbackButton(text="🏢 Работа/офис", payload="occasion:work_office"),
            CallbackButton(text="💼 Собеседование", payload="occasion:interview"),
        ],
        [
            CallbackButton(text="💕 Свидание", payload="occasion:date"),
            CallbackButton(text="🎉 Вечеринка", payload="occasion:party"),
        ],
        [
            CallbackButton(text="🚶 Прогулка", payload="occasion:walk"),
            CallbackButton(text="🏃 Спорт", payload="occasion:sport_active"),
        ],
        [CallbackButton(text="🏠 Меню", payload="action:menu")],
    ])


def season_keyboard() -> AttachmentButton:
    return _inline_kb([
        [CallbackButton(text="❄️ Зима", payload="season:winter")],
        [CallbackButton(text="🍂 Весна/осень", payload="season:demi")],
        [CallbackButton(text="☀️ Лето", payload="season:summer")],
        [CallbackButton(text="🏠 Меню", payload="action:menu")],
    ])


def outfit_reaction_keyboard() -> AttachmentButton:
    return _inline_kb([
        [
            CallbackButton(text="👍 Нравится", payload="outfit:like"),
            CallbackButton(text="🔄 Другой вариант", payload="outfit:reroll"),
        ],
        [
            CallbackButton(text="🏠 Меню", payload="action:menu"),
        ],
    ])


def back_to_menu_keyboard() -> AttachmentButton:
    return _inline_kb([
        [CallbackButton(text="🏠 Меню", payload="action:menu")],
    ])
