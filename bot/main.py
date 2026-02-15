import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.routers import feedback, menu, outfits, subscription, trends, voice, wardrobe
from bot.middlewares.rate_limit import RateLimitMiddleware
from config.logging import setup_logging
from config.settings import settings


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.message.middleware(RateLimitMiddleware())
    dispatcher.include_router(menu.router)
    dispatcher.include_router(wardrobe.router)
    dispatcher.include_router(outfits.router)
    dispatcher.include_router(trends.router)
    dispatcher.include_router(subscription.router)
    dispatcher.include_router(voice.router)
    dispatcher.include_router(feedback.router)
    return dispatcher


async def main() -> None:
    setup_logging(settings.log_level)
    bot = Bot(token=settings.bot_token)
    dispatcher = build_dispatcher()

    await bot.delete_webhook(drop_pending_updates=True)

    logging.info("Bot started")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
