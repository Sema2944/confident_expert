"""Выбор базы, FSM и режима Telegram. Без паролей в логах."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_PG_SCHEMES = ("postgresql://", "postgres://")


def resolve_database_url(db_url: str | None, database_url: str | None) -> str:
    """DB_URL важнее. Пустая строка — SQLite."""
    primary = (db_url or "").strip()
    if primary:
        return primary
    return (database_url or "").strip()


def is_postgres_url(url: str | None) -> bool:
    return (url or "").strip().startswith(_PG_SCHEMES)


def storage_backend_label(url: str | None, sqlite_path: str | None = None) -> str:
    """Текст для лога старта. Пароль из URL не попадает в строку."""
    raw = (url or "").strip()
    if not is_postgres_url(raw):
        if sqlite_path:
            return f"SQLite ({sqlite_path})"
        return "SQLite"
    parsed = urlparse(raw)
    host = parsed.hostname or "unknown"
    port = parsed.port or 5432
    dbname = (parsed.path or "").lstrip("/") or "unknown"
    user = parsed.username or ""
    user_part = f" user={user}" if user else ""
    return f"PostgreSQL host={host} port={port} dbname={dbname}{user_part}"


def normalize_tg_mode(value: str | None) -> str:
    mode = (value or "webhook").strip().lower()
    if mode not in {"webhook", "polling"}:
        raise ValueError("TG_MODE должен быть webhook или polling")
    return mode


def fsm_storage_label(redis_url: str | None) -> str:
    raw = (redis_url or "").strip()
    if not raw:
        return "MemoryStorage"
    parsed = urlparse(raw)
    host = parsed.hostname or "unknown"
    port = parsed.port or 6379
    db = (parsed.path or "").lstrip("/") or "0"
    return f"Redis host={host} port={port} db={db}"


def build_fsm_storage(redis_url: str | None):
    """Память процесса, либо Redis, если задан REDIS_URL.

    Пакет redis импортируется только когда адрес задан.
    """
    raw = (redis_url or "").strip()
    label = fsm_storage_label(raw)
    if not raw:
        from aiogram.fsm.storage.memory import MemoryStorage

        logger.info("FSM storage: %s", label)
        return MemoryStorage()
    try:
        from aiogram.fsm.storage.redis import RedisStorage
    except ImportError as exc:
        raise RuntimeError(
            "REDIS_URL задан, но пакет redis не установлен. "
            "Установите его или уберите REDIS_URL."
        ) from exc
    logger.info("FSM storage: %s", label)
    return RedisStorage.from_url(raw)
