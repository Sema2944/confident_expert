import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.routers import feedback, menu, outfits, payment, search, subscription, survey, trends, voice, wardrobe
from bot.middlewares.rate_limit import RateLimitMiddleware
from bot.storage import init_storage
from config.logging import setup_logging
from config.settings import settings


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.message.middleware(RateLimitMiddleware())
    dispatcher.include_router(menu.router)
    # Сначала глобальные кнопки меню / образов / оплаты — иначе wardrobe_view перехватывает любой текст
    dispatcher.include_router(outfits.router)
    dispatcher.include_router(trends.router)
    dispatcher.include_router(payment.router)
    dispatcher.include_router(subscription.router)
    dispatcher.include_router(wardrobe.router)
    dispatcher.include_router(search.router)
    dispatcher.include_router(voice.router)
    # survey must be before feedback (feedback has catch-all callback handler)
    dispatcher.include_router(survey.router)
    dispatcher.include_router(feedback.router)

    # Universal 🏠 Меню handler — registered last as fallback for any state
    fallback_router = Router(name="fallback_menu")

    @fallback_router.message(F.text == "🏠 Меню", StateFilter("*"))
    async def go_to_menu(message: Message, state: FSMContext) -> None:
        from bot.keyboards import menu_keyboard
        from bot.states import BotStates
        await state.set_state(BotStates.menu)
        await message.answer("Главное меню:", reply_markup=menu_keyboard())

    dispatcher.include_router(fallback_router)

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
    tg_token = (settings.bot_token or "").strip()
    if not tg_token:
        raise RuntimeError(
            "BOT_TOKEN не задан — для Telegram-бота нужен токен (python -m bot.main). "
            "Для только MAX используйте python -m bot_max.max_main."
        )
    await init_storage()
    bot = Bot(token=tg_token)
    dispatcher = build_dispatcher()
    _log_router_overview(dispatcher)

    await bot.delete_webhook(drop_pending_updates=True)

    logging.info("Bot started")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
