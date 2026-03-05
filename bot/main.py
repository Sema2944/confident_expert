import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent

from bot.routers import feedback, menu, outfits, payment, search, subscription, survey, trends, voice, wardrobe
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.storage import init_storage
from config.logging import setup_logging
from config.settings import settings


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.message.middleware(RateLimitMiddleware())
    dispatcher.include_router(menu.router)
    dispatcher.include_router(wardrobe.router)
    dispatcher.include_router(outfits.router)
    dispatcher.include_router(trends.router)
    dispatcher.include_router(payment.router)
    dispatcher.include_router(subscription.router)
    dispatcher.include_router(search.router)
    dispatcher.include_router(voice.router)
    # survey must be before feedback (feedback has catch-all callback handler)
    dispatcher.include_router(survey.router)
    dispatcher.include_router(feedback.router)

    @dispatcher.error()
    async def global_error_handler(event: ErrorEvent, bot: Bot) -> None:
        logging.exception("Unhandled error: %s", event.exception)
        try:
            from services.admin_notify_service import AdminNotifyService
            from bot.storage import increment_daily_stat
            await increment_daily_stat("errors_count")
            error_text = (
                f"🔴 <b>Ошибка</b>\n"
                f"{type(event.exception).__name__}: {str(event.exception)[:300]}"
            )
            await AdminNotifyService.notify(bot, error_text)
        except Exception:
            pass

    return dispatcher


def _log_router_overview(dispatcher: Dispatcher) -> None:
    routers = list(getattr(dispatcher, "sub_routers", []))
    logging.info("Connected routers (%s): %s", len(routers), ", ".join(router.name for router in routers))

    for router in routers:
        callback_handlers = len(router.observers["callback_query"].handlers)
        logging.info("Router '%s' callback_query handlers: %s", router.name, callback_handlers)


async def main() -> None:
    setup_logging(settings.log_level)
    await init_storage()
    bot = Bot(token=settings.bot_token)
    dispatcher = build_dispatcher()
    _log_router_overview(dispatcher)

    await bot.delete_webhook(drop_pending_updates=True)

    logging.info("Bot started")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
