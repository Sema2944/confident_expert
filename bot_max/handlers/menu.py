"""MAX: /start, меню, навигация."""

import logging

from maxapi import Router, F
from maxapi.context import MemoryContext
from maxapi.types import BotStarted, MessageCreated, MessageCallback, Command

from bot.storage import get_items, get_user_location
from bot.utils.messages import START_MESSAGE, HELP_MESSAGE
from bot_max.keyboards import menu_keyboard, back_to_menu_keyboard
from bot_max.states import MaxStates
from services.wardrobe_analysis_service import analyze_wardrobe_gaps

logger = logging.getLogger(__name__)

router = Router()


@router.bot_started()
async def on_bot_started(event: BotStarted, context: MemoryContext):
    """Пользователь нажал «Начать» (аналог /start)."""
    logger.info("MAX bot_started from user %s, chat %s", event.user.user_id, event.chat_id)
    user_id = event.user.user_id
    from services.subscription_service import get_or_create_user
    await get_or_create_user(user_id)

    items = await get_items(user_id)
    if not items:
        text = f"{START_MESSAGE}\n\nОтправь фото первой вещи — я добавлю её в гардероб."
    else:
        gaps = analyze_wardrobe_gaps(items)
        text = f"{START_MESSAGE}\n\n{gaps}" if gaps else START_MESSAGE

    await context.set_state(MaxStates.menu)
    await event.bot.send_message(
        chat_id=event.chat_id,
        text=text,
        attachments=[menu_keyboard()],
    )


@router.message_created(Command("start"))
async def cmd_start(event: MessageCreated, context: MemoryContext):
    if not event.message.sender:
        logger.warning("MAX /start: message without sender")
        return
    logger.info("MAX /start from user %s", event.message.sender.user_id)
    user_id = event.message.sender.user_id
    from services.subscription_service import get_or_create_user
    await get_or_create_user(user_id)

    items = await get_items(user_id)
    if not items:
        text = f"{START_MESSAGE}\n\nОтправь фото первой вещи — я добавлю её в гардероб."
    else:
        gaps = analyze_wardrobe_gaps(items)
        text = f"{START_MESSAGE}\n\n{gaps}" if gaps else START_MESSAGE

    await context.set_state(MaxStates.menu)
    await event.message.answer(text, attachments=[menu_keyboard()])


@router.message_created(Command("help"))
async def cmd_help(event: MessageCreated):
    await event.message.answer(HELP_MESSAGE)


@router.message_created(Command("menu"))
async def cmd_menu(event: MessageCreated, context: MemoryContext):
    await context.set_state(MaxStates.menu)
    await event.message.answer("Меню:", attachments=[menu_keyboard()])


@router.message_callback(F.callback.payload == "action:menu")
async def cb_menu(event: MessageCallback, context: MemoryContext):
    await event.answer()
    await context.set_state(MaxStates.menu)
    chat_id = event.message.recipient.chat_id if event.message else None
    if chat_id:
        await event.bot.send_message(
            chat_id=chat_id,
            text="Меню:",
            attachments=[menu_keyboard()],
        )


@router.message_created()
async def on_any_message(event: MessageCreated, context: MemoryContext):
    """Catch-all: любое текстовое сообщение без команды → показать меню."""
    if not event.message.sender:
        logger.warning("MAX message_created: no sender, skip")
        return
    body = event.message.body
    text = body.text if body else None
    user_id = event.message.sender.user_id
    logger.info("MAX got message: %r from user %s", text, user_id)
    await context.set_state(MaxStates.menu)
    await event.message.answer(
        "Выбери действие в меню 👇",
        attachments=[menu_keyboard()],
    )
