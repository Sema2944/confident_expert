"""Короткий лог входящих апдейтов: тип, user_id, команда или callback."""

from __future__ import annotations

import logging

from aiogram import BaseMiddleware

logger = logging.getLogger(__name__)

_COMMAND_MAX = 64
_CALLBACK_MAX = 80


def _command_token(text: str | None) -> str | None:
    if not text:
        return None
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    token = stripped.split(maxsplit=1)[0]
    token = token.split("@", 1)[0]
    return token[:_COMMAND_MAX] or None


def _user_id_of(obj: object) -> int | None:
    user = getattr(obj, "from_user", None)
    if user is None:
        user = getattr(obj, "user", None)
    user_id = getattr(user, "id", None)
    return user_id if isinstance(user_id, int) else None


def _describe_message(message: object, prefix: str = "") -> tuple[str, int | None, str | None]:
    user_id = _user_id_of(message)
    command = _command_token(getattr(message, "text", None))
    if command:
        return f"{prefix}command", user_id, command
    if getattr(message, "photo", None):
        return f"{prefix}photo", user_id, None
    if getattr(message, "voice", None) or getattr(message, "audio", None):
        return f"{prefix}voice", user_id, None
    if getattr(message, "video", None) or getattr(message, "video_note", None):
        return f"{prefix}video", user_id, None
    if getattr(message, "document", None):
        return f"{prefix}document", user_id, None
    if getattr(message, "sticker", None):
        return f"{prefix}sticker", user_id, None
    if getattr(message, "location", None):
        return f"{prefix}location", user_id, None
    if getattr(message, "contact", None):
        return f"{prefix}contact", user_id, None
    return f"{prefix}message", user_id, None


def describe_incoming_update(event: object) -> tuple[str, int | None, str | None]:
    """Возвращает (тип, user_id, команда или callback). Текст и подписи не возвращает."""
    message = getattr(event, "message", None)
    if message is not None:
        return _describe_message(message)
    edited = getattr(event, "edited_message", None)
    if edited is not None:
        return _describe_message(edited, prefix="edited_")
    callback = getattr(event, "callback_query", None)
    if callback is not None:
        data = getattr(callback, "data", None) or ""
        action = data[:_CALLBACK_MAX] or None
        return "callback_query", _user_id_of(callback), action
    for kind in (
        "inline_query",
        "chosen_inline_result",
        "channel_post",
        "edited_channel_post",
        "poll",
        "poll_answer",
        "pre_checkout_query",
        "shipping_query",
        "my_chat_member",
        "chat_member",
    ):
        payload = getattr(event, kind, None)
        if payload is not None:
            return kind, _user_id_of(payload), None
    return "update", _user_id_of(event), None


class IncomingUpdateLogMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        kind, user_id, action = describe_incoming_update(event)
        logger.info("Incoming update type=%s user_id=%s action=%s", kind, user_id, action)
        return await handler(event, data)
