import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bot.main import build_dispatcher, log_telegram_identity
from bot.scheduler import start_schedulers
from bot.storage import init_storage
from config.logging import setup_logging
from config.settings import settings
from services.payment_service import client_ip_from_headers, handle_yookassa_notification, init_yookassa


async def on_startup(bot: Bot) -> None:
    webhook_base = os.getenv("WEBHOOK_BASE")
    webhook_path = os.getenv("WEBHOOK_PATH", "/tg/webhook")
    _sec = (os.getenv("WEBHOOK_SECRET") or "").strip()
    webhook_secret = _sec if _sec else None

    if not webhook_base:
        raise RuntimeError("WEBHOOK_BASE is not set")

    webhook_url = f"{webhook_base}{webhook_path}"

    # Сбрасываем старое и ставим новое
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(
        url=webhook_url,
        secret_token=webhook_secret,
        drop_pending_updates=True,
        allowed_updates=[
            "message",
            "callback_query",
            "inline_query",
            "chosen_inline_result",
            "channel_post",
            "edited_message",
            "shipping_query",
            "pre_checkout_query",
            "poll",
            "poll_answer",
            "my_chat_member",
            "chat_member",
        ],
    )
    logging.info(f"Webhook set to: {webhook_url}")


async def on_shutdown(bot: Bot) -> None:
    await bot.delete_webhook()
    await bot.session.close()
    logging.info("Webhook deleted, session closed")


async def main() -> None:
    setup_logging(settings.log_level)
    await init_storage()

    init_yookassa()

    tg_token = (settings.bot_token or "").strip()
    if not tg_token:
        raise RuntimeError("BOT_TOKEN is required for Telegram webhook mode")
    bot = Bot(token=tg_token)
    await log_telegram_identity(bot)
    dp: Dispatcher = build_dispatcher()

    # aiohttp app
    app = web.Application()

    # Healthcheck endpoint (Render любит)
    async def health(_: web.Request) -> web.Response:
        return web.Response(text="OK")

    app.router.add_get("/", health)

    async def yookassa_webhook(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            logging.exception("YooKassa webhook is not JSON")
            return web.Response(text="Bad Request", status=400)
        source_ip = client_ip_from_headers(
            request.headers.get("X-Forwarded-For"),
            request.remote,
        )
        try:
            result = await handle_yookassa_notification(body=body, source_ip=source_ip)
        except Exception:
            logging.exception("YooKassa webhook error")
            return web.Response(text="Error", status=500)
        logging.info(
            "YooKassa webhook result=%s user_id=%s",
            result["reason"],
            result["user_id"],
        )
        if result["activated"] and result["user_id"]:
            user_id = result["user_id"]
            try:
                from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
                from services.pricing import renewal_notice
                await bot.send_message(
                    user_id,
                    "✅ Клуб включён.\n\n"
                    f"{renewal_notice()}\n\n"
                    "Хочешь получать готовый образ каждое утро? "
                    "Я подберу по погоде и твоему расписанию.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="☀️ Да, присылай в 8:00", callback_data="push:enable:8")],
                        [InlineKeyboardButton(text="🕐 В другое время", callback_data="push:select_time")],
                        [InlineKeyboardButton(text="❌ Нет, спасибо", callback_data="push:disable")],
                    ]),
                )
            except Exception:
                logging.exception("Failed to send subscription confirmation to user %s", user_id)
            try:
                from services.admin_notify_service import AdminNotifyService
                from bot.storage import increment_daily_stat
                await increment_daily_stat("new_subscriptions")
                await AdminNotifyService.notify(
                    bot,
                    f"💎 <b>Новая оплата клуба</b>\nПользователь {user_id}, {result['days']} дн.",
                )
            except Exception:
                logging.exception("Failed to send admin payment notification")
        text = "OK" if result["status"] == 200 else result["reason"]
        return web.Response(text=text, status=result["status"])

    app.router.add_post("/yookassa/webhook", yookassa_webhook)

    webhook_path = os.getenv("WEBHOOK_PATH", "/tg/webhook")
    _sec = (os.getenv("WEBHOOK_SECRET") or "").strip()
    webhook_secret = _sec if _sec else None

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
    if settings.max_bot_token:
        from bot_max.max_main import run_max_bot
        asyncio.create_task(run_max_bot())
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    logging.info(f"Webhook server started on 0.0.0.0:{port}")

    scheduler_tasks = await start_schedulers(bot)

    # держим процесс живым
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        for task in scheduler_tasks:
            task.cancel()
        await on_shutdown(bot)
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
