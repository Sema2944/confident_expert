import logging

from aiogram import Bot

from config.settings import settings


class AdminNotifyService:
    @staticmethod
    async def notify(bot: Bot, text: str) -> None:
        if not settings.admin_id:
            return
        try:
            await bot.send_message(settings.admin_id, text, parse_mode="HTML")
        except Exception:
            logging.exception("AdminNotifyService: failed to send notification")
