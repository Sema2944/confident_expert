"""Гарантируем валидные настройки до импорта модулей, тянущих config.settings."""

import os

# Settings требует BOT_TOKEN и/или MAX_BOT_TOKEN; в CI без .env — подставляем заглушку.
os.environ.setdefault("BOT_TOKEN", "123456:FAKE_TELEGRAM_TOKEN_FOR_PYTEST")
