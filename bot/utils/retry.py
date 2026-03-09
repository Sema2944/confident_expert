"""Retry helpers for Telegram API rate limits."""

import asyncio
import logging

from aiogram.exceptions import TelegramRetryAfter

logger = logging.getLogger(__name__)


async def safe_answer_photo(target, **kwargs):
    """answer_photo with automatic retry on TelegramRetryAfter."""
    try:
        return await target.answer_photo(**kwargs)
    except TelegramRetryAfter as e:
        logger.warning("TelegramRetryAfter: sleeping %s seconds", e.retry_after)
        await asyncio.sleep(e.retry_after + 1)
        return await target.answer_photo(**kwargs)
