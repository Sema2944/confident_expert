"""Перенос данных из SQLite в Postgres. Повторный запуск не затирает уже скопированные строки.

Схема в Postgres создаётся этим скриптом (CREATE TABLE IF NOT EXISTS) и ещё раз
при старте бота. Существующие строки в Postgres остаются: INSERT ... ON CONFLICT DO NOTHING.

Запуск из корня репозитория, когда в окружении уже есть DB_URL или DATABASE_URL:

    python scripts/sqlite_to_postgres.py
    python scripts/sqlite_to_postgres.py /path/to/wardrobe.sqlite3
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

# Имя таблицы -> столбцы первичного ключа. Только эти таблицы переносим.
TABLE_KEYS: dict[str, tuple[str, ...]] = {
    "user_profiles": ("user_id",),
    "wardrobe_items": ("id",),
    "feedback_messages": ("id",),
    "outfit_feedback": ("id",),
    "outfit_history": ("id",),
    "survey_feedback": ("id",),
    "daily_stats": ("date",),
    "wardrobe_capsules": ("id",),
    "capsule_items": ("capsule_id", "item_id"),
    "club_members": ("user_id",),
    "payment_records": ("payment_id",),
    "scheduled_posts": ("id",),
    "user_scheduler_claims": ("claim_key",),
}

SERIAL_ID_TABLES = {
    "wardrobe_items",
    "feedback_messages",
    "outfit_feedback",
    "outfit_history",
    "survey_feedback",
    "wardrobe_capsules",
    "scheduled_posts",
}

_IDENT = __import__("re").compile(r"^[a-z_][a-z0-9_]*$")


def build_upsert_sql(table: str, columns: list[str], pk: tuple[str, ...], *, dollar: bool) -> str:
    if not _IDENT.match(table) or table not in TABLE_KEYS:
        raise ValueError(f"unexpected table {table}")
    for name in list(columns) + list(pk):
        if not _IDENT.match(name):
            raise ValueError(f"unexpected column {name}")
    if not set(pk).issubset(columns):
        raise ValueError(f"{table}: primary key {pk} is not in {columns}")
    cols = ", ".join(columns)
    if dollar:
        values = ", ".join(f"${index}" for index in range(1, len(columns) + 1))
    else:
        values = ", ".join("?" for _ in columns)
    conflict = ", ".join(pk)
    return (
        f"INSERT INTO {table} ({cols}) VALUES ({values}) "
        f"ON CONFLICT ({conflict}) DO NOTHING"
    )


def _split_sql(script: str) -> list[str]:
    return [part.strip() for part in script.split(";") if part.strip()]


def postgres_ddl_statements() -> list[str]:
    from bot.storage import _PG_SCHEMA

    extra = """
    CREATE TABLE IF NOT EXISTS club_members (
        user_id BIGINT PRIMARY KEY,
        trial_paid INTEGER NOT NULL DEFAULT 0,
        club_paid INTEGER NOT NULL DEFAULT 0,
        intro_slot INTEGER,
        intro_months_used INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS payment_records (
        payment_id TEXT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        amount_rub INTEGER NOT NULL,
        kind TEXT NOT NULL,
        days INTEGER NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS scheduled_posts (
        id SERIAL PRIMARY KEY,
        scheduled_at TEXT NOT NULL,
        post_type TEXT NOT NULL DEFAULT 'text',
        text_content TEXT,
        poll_question TEXT,
        poll_options_json TEXT,
        channel_id TEXT NOT NULL DEFAULT '@shkaf_rabotaet',
        status TEXT NOT NULL DEFAULT 'pending',
        sent_at TEXT,
        error_message TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_scheduled_posts_status_time
        ON scheduled_posts (status, scheduled_at);
    CREATE TABLE IF NOT EXISTS user_scheduler_claims (
        claim_key TEXT PRIMARY KEY,
        created_at TEXT NOT NULL
    );
    """
    return _split_sql(_PG_SCHEMA) + _split_sql(extra)


def _sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row[0] for row in rows}


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def copy_table_sqlite(src: sqlite3.Connection, dest: sqlite3.Connection, table: str) -> int:
    """Та же вставка, что и в Postgres, но через sqlite3 — для проверки идемпотентности."""
    pk = TABLE_KEYS[table]
    columns = [name for name in _sqlite_columns(src, table) if name in _sqlite_columns(dest, table)]
    sql = build_upsert_sql(table, columns, pk, dollar=False)
    inserted = 0
    query = f"SELECT {', '.join(columns)} FROM {table}"
    for row in src.execute(query):
        cursor = dest.execute(sql, tuple(row))
        if cursor.rowcount:
            inserted += 1
    dest.commit()
    return inserted


async def migrate(sqlite_path: Path, dsn: str) -> dict[str, int]:
    import asyncpg

    if not sqlite_path.is_file():
        raise SystemExit(f"Файл SQLite не найден: {sqlite_path}")

    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    conn = await asyncpg.connect(dsn)
    copied: dict[str, int] = {}
    try:
        for statement in postgres_ddl_statements():
            await conn.execute(statement)
        present = _sqlite_tables(src)
        for table, pk in TABLE_KEYS.items():
            if table not in present:
                continue
            pg_columns = [
                row["column_name"]
                for row in await conn.fetch(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = $1
                    ORDER BY ordinal_position
                    """,
                    table,
                )
            ]
            columns = [name for name in _sqlite_columns(src, table) if name in pg_columns]
            if not columns or not set(pk).issubset(columns):
                print(f"skip {table}: нет общих столбцов ключа")
                continue
            sql = build_upsert_sql(table, columns, pk, dollar=True)
            inserted = 0
            for row in src.execute(f"SELECT {', '.join(columns)} FROM {table}"):
                values = tuple(row[name] for name in columns)
                status = await conn.execute(sql, *values)
                if status.endswith(" 1"):
                    inserted += 1
            copied[table] = inserted
            if table in SERIAL_ID_TABLES and "id" in columns:
                await conn.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', 'id'),
                        GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 1), 1),
                        true
                    )
                    """
                )
            print(f"{table}: новых строк {inserted}")
    finally:
        await conn.close()
        src.close()
    return copied


def main() -> None:
    dsn = (os.environ.get("DB_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if not dsn.startswith(("postgresql://", "postgres://")):
        raise SystemExit("Задайте DB_URL или DATABASE_URL с адресом postgresql://…")
    if len(sys.argv) > 1:
        sqlite_path = Path(sys.argv[1])
    else:
        default = os.environ.get("WARDROBE_STORAGE_PATH", str(ROOT / "data" / "wardrobe.sqlite3"))
        sqlite_path = Path(default)
    asyncio.run(migrate(sqlite_path, dsn))


if __name__ == "__main__":
    main()
