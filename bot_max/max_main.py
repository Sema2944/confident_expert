"""Точка входа MAX-бота. Polling-режим."""

import asyncio
import logging
import os

from maxapi import Bot, Dispatcher

from config.logging import setup_logging
from config.settings import settings
from bot.storage import init_storage


def _max_token() -> str:
    """Токен из pydantic-settings или напрямую из окружения (Render)."""
    return (settings.max_bot_token or os.environ.get("MAX_BOT_TOKEN") or "").strip()


async def main():
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    token = _max_token()
    if not token:
        logger.error(
            "MAX_BOT_TOKEN не задан — MAX-бот не запускается. "
            "Добавьте MAX_BOT_TOKEN в Render / .env."
        )
        return

    bot = Bot(token)

    # Диагностика в логах Render: токен и webhook до снятия
    try:
        me = await bot.get_me()
        logger.info(
            "MAX: get_me OK — bot user_id=%s username=%s",
            getattr(me, "user_id", None),
            getattr(me, "username", None),
        )
    except Exception:
        logger.exception("MAX: get_me failed — проверьте MAX_BOT_TOKEN (401 / InvalidToken)")

    try:
        subs = await bot.get_subscriptions()
        if subs.subscriptions:
            logger.warning(
                "MAX: активны webhook-подписки (%s) — polling их не видит, снимаем",
                len(subs.subscriptions),
            )
            for s in subs.subscriptions:
                logger.warning("MAX: webhook → %s", s.url)
        else:
            logger.info("MAX: webhook-подписок нет")
    except Exception:
        logger.exception("MAX: get_subscriptions failed")

    # Если в кабинете MAX включён webhook, long polling не получает апдейты.
    try:
        await bot.delete_webhook()
        logger.info("MAX: delete_webhook выполнен — дальше только long polling")
    except Exception:
        logger.exception("MAX: delete_webhook failed (продолжаем polling)")

    dp = Dispatcher()

    # Регистрация роутеров
    from bot_max.handlers.menu import router as menu_router
    from bot_max.handlers.outfits import router as outfits_router
    from bot_max.handlers.payment import router as payment_router
    from bot_max.handlers.wardrobe import router as wardrobe_router

    # menu_router последним — в нём catch-all хендлер для необработанных сообщений
    dp.include_routers(outfits_router, wardrobe_router, payment_router, menu_router)

    await init_storage()

    logger.info("MAX bot starting polling…")
    await dp.start_polling(bot)


run_max_bot = main

if __name__ == "__main__":
    asyncio.run(main())
