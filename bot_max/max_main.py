"""Точка входа MAX-бота. Polling-режим."""

import asyncio
import logging
import os

from maxapi import Bot, Dispatcher
from maxapi.types.updates.message_callback import MessageCallback as _MaxMessageCallback


_orig_callback_answer = _MaxMessageCallback.answer


async def _safe_callback_answer(self, *args, **kwargs):
    """MAX API может вернуть 400 (proto.payload / buttons cannot be null) на пустой ответ.

    Делаем вызов безопасным, чтобы хэндлеры не падали из-за «беззвучного» подтверждения
    callback-кнопки (для UX это не критично).
    """
    try:
        return await _orig_callback_answer(self, *args, **kwargs)
    except Exception as exc:  # pragma: no cover — внешний API
        logging.getLogger("bot_max.max_main").warning(
            "MAX message_callback answer ignored due to API error: %s", exc
        )
        return None


_MaxMessageCallback.answer = _safe_callback_answer  # type: ignore[assignment]

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

    me_user_id: int | None = None
    me_username: str | None = None
    try:
        me = await bot.get_me()
        me_user_id = getattr(me, "user_id", None)
        me_username = getattr(me, "username", None)
        if me_user_id is None:
            logger.error(
                "MAX: get_me вернул Error/без user_id (вероятно, MAX_BOT_TOKEN недействителен "
                "или сервер MAX ответил 403 deprecated.token из-за старой версии maxapi). "
                "Проверьте токен в @MasterBot и обновите MAX_BOT_TOKEN в Render."
            )
            return
        logger.info("MAX: get_me OK — user_id=%s username=%s", me_user_id, me_username)
    except Exception:
        logger.exception("MAX: get_me failed — проверьте MAX_BOT_TOKEN (401 / InvalidToken)")
        return

    if hasattr(bot, "get_subscriptions"):
        try:
            subs = await bot.get_subscriptions()
            urls = [s.url for s in (getattr(subs, "subscriptions", None) or [])]
            if urls:
                logger.warning("MAX: активны webhook-подписки (%s) — снимаем для polling", len(urls))
                for u in urls:
                    logger.warning("MAX: webhook → %s", u)
            else:
                logger.info("MAX: webhook-подписок нет")
        except Exception:
            logger.exception("MAX: get_subscriptions failed (не критично)")

    if hasattr(bot, "delete_webhook"):
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
