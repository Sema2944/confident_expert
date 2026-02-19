import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bot.main import build_dispatcher
from bot.storage import init_storage
from config.logging import setup_logging
from config.settings import settings


async def on_startup(bot: Bot) -> None:
    webhook_base = os.getenv("WEBHOOK_BASE")
    webhook_path = os.getenv("WEBHOOK_PATH", "/tg/webhook")
    webhook_secret = os.getenv("WEBHOOK_SECRET")

    if not webhook_base:
        raise RuntimeError("WEBHOOK_BASE is not set")

    webhook_url = f"{webhook_base}{webhook_path}"

    # Сбрасываем старое и ставим новое
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(
        url=webhook_url,
        secret_token=webhook_secret,
        drop_pending_updates=True,
    )
    logging.info(f"Webhook set to: {webhook_url}")


async def on_shutdown(bot: Bot) -> None:
    await bot.delete_webhook()
    await bot.session.close()
    logging.info("Webhook deleted, session closed")


async def main() -> None:
    setup_logging(settings.log_level)
    await init_storage()

    bot = Bot(token=settings.bot_token)
    dp: Dispatcher = build_dispatcher()

    # aiohttp app
    app = web.Application()

    # Healthcheck endpoint (Render любит)
    async def health(_: web.Request) -> web.Response:
        return web.Response(text="OK")

    app.router.add_get("/", health)

    webhook_path = os.getenv("WEBHOOK_PATH", "/tg/webhook")
    webhook_secret = os.getenv("WEBHOOK_SECRET")

    # Регистрируем webhook handler
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=webhook_secret,
    ).register(app, path=webhook_path)

    setup_application(app, dp, bot=bot)

    # Ставим webhook
    await on_startup(bot)

    port = int(os.getenv("PORT", "10000"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    logging.info(f"Webhook server started on 0.0.0.0:{port}")

    # держим процесс живым
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await on_shutdown(bot)
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
