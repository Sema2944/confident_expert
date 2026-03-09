"""Точка входа MAX-бота. Polling-режим."""

import asyncio
import logging

from maxapi import Bot, Dispatcher

from config.settings import settings
from bot.storage import init_storage


async def main():
    if not settings.max_bot_token:
        logging.error("MAX_BOT_TOKEN not set — MAX bot disabled")
        return

    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    logger = logging.getLogger(__name__)

    bot = Bot(settings.max_bot_token)
    dp = Dispatcher()

    # Регистрация роутеров
    from bot_max.handlers.menu import router as menu_router
    from bot_max.handlers.wardrobe import router as wardrobe_router
    from bot_max.handlers.outfits import router as outfits_router
    from bot_max.handlers.payment import router as payment_router

    # menu_router последним — в нём catch-all хендлер для необработанных сообщений
    dp.include_routers(outfits_router, wardrobe_router, payment_router, menu_router)

    await init_storage()

    logger.info("MAX bot starting polling…")
    await dp.start_polling(bot)


run_max_bot = main

if __name__ == "__main__":
    asyncio.run(main())
