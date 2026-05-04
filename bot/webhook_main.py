import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from bot.main import build_dispatcher
from bot.scheduler import init_scheduled_posts_table, scheduler_loop, seed_week1_posts, seed_week2_posts
from bot.storage import init_storage
from config.logging import setup_logging
from config.settings import settings
from services.payment_service import init_yookassa, parse_webhook
from services.subscription_service import activate_subscription


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
    await init_scheduled_posts_table()
    await seed_week1_posts()
    await seed_week2_posts()

    init_yookassa()

    tg_token = (settings.bot_token or "").strip()
    if not tg_token:
        raise RuntimeError("BOT_TOKEN is required for Telegram webhook mode")
    bot = Bot(token=tg_token)
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
            event_type, user_id = parse_webhook(body)
            logging.info("YooKassa webhook: event=%s user_id=%s", event_type, user_id)
            if event_type == "payment.succeeded" and user_id:
                await activate_subscription(user_id, settings.subscription_days)
                try:
                    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
                    await bot.send_message(
                        user_id,
                        "✅ Подписка активирована!\n\n"
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
                        f"💎 <b>Новая подписка</b>\nПользователь {user_id} оформил подписку на {settings.subscription_days} дней",
                    )
                except Exception:
                    logging.exception("Failed to send admin payment notification")
            return web.Response(text="OK", status=200)
        except Exception:
            logging.exception("YooKassa webhook error")
            return web.Response(text="Error", status=500)

    app.router.add_post("/yookassa/webhook", yookassa_webhook)

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
    if settings.max_bot_token:
        from bot_max.max_main import run_max_bot
        asyncio.create_task(run_max_bot())
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    logging.info(f"Webhook server started on 0.0.0.0:{port}")

    # запускаем планировщик автопостинга
    scheduler_task = asyncio.create_task(scheduler_loop(bot))

    # держим процесс живым
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        scheduler_task.cancel()
        await on_shutdown(bot)
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
