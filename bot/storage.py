from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import asynccontextmanager

from config.settings import settings

logger = logging.getLogger(__name__)

# ─── Backend detection ──────────────────────────────────────────
_USE_PG = bool(settings.db_url)

_STORAGE_PATH = Path(
    os.getenv("WARDROBE_STORAGE_PATH", Path(__file__).resolve().parents[1] / "data" / "wardrobe.sqlite3")
)
_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)

_pg_pool = None


def _ph(index: int) -> str:
    """Placeholder: $1 for PG, ? for SQLite."""
    return f"${index}" if _USE_PG else "?"


def _now_ts() -> datetime | str:
    """Current timestamp: datetime for PG (TIMESTAMPTZ), ISO string for SQLite."""
    if _USE_PG:
        return datetime.now(timezone.utc)
    return datetime.now().isoformat()


# ─── Connection helpers ─────────────────────────────────────────


async def _init_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        import asyncpg
        _pg_pool = await asyncpg.create_pool(settings.db_url, min_size=2, max_size=10)
        logger.info("PostgreSQL pool created")


class _PgConnection:
    """Thin wrapper around asyncpg connection to unify interface with aiosqlite."""

    def __init__(self, conn):
        self._conn = conn
        self._last_result = None

    async def execute(self, sql: str, params: tuple = ()) -> "_PgConnection":
        self._last_result = await self._conn.execute(sql, *params)
        return self

    async def fetch(self, sql: str, params: tuple = ()) -> list[dict]:
        rows = await self._conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    async def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        row = await self._conn.fetchrow(sql, *params)
        return dict(row) if row else None

    async def fetchval(self, sql: str, params: tuple = ()):
        return await self._conn.fetchval(sql, *params)

    async def commit(self):
        pass  # asyncpg auto-commits


class _SqliteConnection:
    """Thin wrapper around aiosqlite connection to match _PgConnection interface."""

    def __init__(self, conn):
        self._conn = conn
        self._last_cursor = None

    async def execute(self, sql: str, params: tuple = ()) -> "_SqliteConnection":
        self._last_cursor = await self._conn.execute(sql, params)
        return self

    async def fetch(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetchval(self, sql: str, params: tuple = ()):
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        return row[0] if row else None

    async def commit(self):
        await self._conn.commit()

    @property
    def lastrowid(self) -> int:
        return self._last_cursor.lastrowid if self._last_cursor else 0

    @property
    def rowcount(self) -> int:
        return self._last_cursor.rowcount if self._last_cursor else 0


@asynccontextmanager
async def _connect():
    if _USE_PG:
        await _init_pg_pool()
        async with _pg_pool.acquire() as conn:
            yield _PgConnection(conn)
    else:
        import aiosqlite
        async with aiosqlite.connect(_STORAGE_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            yield _SqliteConnection(conn)


# ─── Table creation ──────────────────────────────────────────────

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS wardrobe_items (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    category TEXT NOT NULL,
    telegram_file_id TEXT NOT NULL,
    processed_file_id TEXT,
    display_name TEXT,
    metadata_json TEXT NOT NULL,
    price INTEGER DEFAULT 0,
    photo_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedback_messages (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    text TEXT NOT NULL,
    contact TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS outfit_feedback (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    occasion TEXT,
    season TEXT,
    action TEXT NOT NULL,
    items_json TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    trial_used INTEGER DEFAULT 0,
    subscription_status TEXT DEFAULT 'inactive',
    subscription_until TIMESTAMPTZ,
    outfit_requests_count INTEGER DEFAULT 0,
    city TEXT DEFAULT 'Москва',
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    paywall_hit_at TIMESTAMPTZ,
    morning_push_enabled INTEGER DEFAULT 0,
    morning_push_hour INTEGER DEFAULT 8,
    survey_shown_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS outfit_history (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    outfit_items TEXT NOT NULL,
    occasion TEXT,
    season TEXT,
    liked INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outfit_history_user_date ON outfit_history (user_id, created_at);

CREATE TABLE IF NOT EXISTS survey_feedback (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    rating INTEGER,
    most_valuable TEXT,
    free_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,
    new_subscriptions INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0
);
"""


async def _init_pg() -> None:
    """Create all tables in PostgreSQL."""
    await _init_pg_pool()
    async with _pg_pool.acquire() as conn:
        await conn.execute(_PG_SCHEMA)
    logger.info("PostgreSQL schema initialized")


async def _init_sqlite() -> None:
    """Create all tables in SQLite with PRAGMA-based migrations."""
    import aiosqlite
    async with aiosqlite.connect(_STORAGE_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS wardrobe_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                telegram_file_id TEXT NOT NULL,
                processed_file_id TEXT,
                display_name TEXT,
                metadata_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor = await connection.execute("PRAGMA table_info(wardrobe_items)")
        columns = {row["name"] for row in await cursor.fetchall()}
        if "processed_file_id" not in columns:
            await connection.execute("ALTER TABLE wardrobe_items ADD COLUMN processed_file_id TEXT")
        if "display_name" not in columns:
            await connection.execute("ALTER TABLE wardrobe_items ADD COLUMN display_name TEXT")
        if "price" not in columns:
            await connection.execute("ALTER TABLE wardrobe_items ADD COLUMN price INTEGER DEFAULT 0")
        if "photo_url" not in columns:
            await connection.execute("ALTER TABLE wardrobe_items ADD COLUMN photo_url TEXT")
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                contact TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS outfit_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                occasion TEXT,
                season TEXT,
                action TEXT NOT NULL,
                items_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                trial_used INTEGER DEFAULT 0,
                subscription_status TEXT DEFAULT 'inactive',
                subscription_until DATETIME,
                outfit_requests_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        user_cols = {row["name"] for row in await (await connection.execute("PRAGMA table_info(user_profiles)")).fetchall()}
        if "city" not in user_cols:
            await connection.execute("ALTER TABLE user_profiles ADD COLUMN city TEXT DEFAULT 'Москва'")
        if "lat" not in user_cols:
            await connection.execute("ALTER TABLE user_profiles ADD COLUMN lat REAL")
        if "lon" not in user_cols:
            await connection.execute("ALTER TABLE user_profiles ADD COLUMN lon REAL")
        if "paywall_hit_at" not in user_cols:
            await connection.execute("ALTER TABLE user_profiles ADD COLUMN paywall_hit_at DATETIME")
        if "morning_push_enabled" not in user_cols:
            await connection.execute("ALTER TABLE user_profiles ADD COLUMN morning_push_enabled INTEGER DEFAULT 0")
        if "morning_push_hour" not in user_cols:
            await connection.execute("ALTER TABLE user_profiles ADD COLUMN morning_push_hour INTEGER DEFAULT 8")

        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS outfit_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                outfit_items TEXT NOT NULL,
                occasion TEXT,
                season TEXT,
                liked INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_outfit_history_user_date ON outfit_history (user_id, created_at)"
        )

        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS survey_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                rating INTEGER,
                most_valuable TEXT,
                free_text TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                new_subscriptions INTEGER DEFAULT 0,
                errors_count INTEGER DEFAULT 0
            )
            """
        )

        if "survey_shown_at" not in user_cols:
            await connection.execute("ALTER TABLE user_profiles ADD COLUMN survey_shown_at DATETIME")

        await connection.commit()


async def init_storage() -> None:
    if _USE_PG:
        await _init_pg()
    else:
        await _init_sqlite()


# ─── Outfit Feedback ─────────────────────────────────────────────


async def log_outfit_feedback(
    user_id: int, occasion: str, season: str, action: str, items: dict,
) -> None:
    async with _connect() as db:
        await db.execute(
            f"INSERT INTO outfit_feedback (user_id, occasion, season, action, items_json) "
            f"VALUES ({_ph(1)}, {_ph(2)}, {_ph(3)}, {_ph(4)}, {_ph(5)})",
            (user_id, occasion, season, action, json.dumps(items, ensure_ascii=False)),
        )
        await db.commit()


async def get_liked_items(user_id: int) -> list[str]:
    async with _connect() as db:
        rows = await db.fetch(
            f"SELECT items_json FROM outfit_feedback "
            f"WHERE user_id = {_ph(1)} AND action = 'like' "
            f"ORDER BY created_at DESC LIMIT 20",
            (user_id,),
        )

    file_ids: list[str] = []
    for row in rows:
        items = json.loads(row["items_json"])
        for fids in items.values():
            if isinstance(fids, list):
                file_ids.extend(fids)
    return file_ids


# ─── Wardrobe Items ──────────────────────────────────────────────

_ITEM_COLS = "id, category, telegram_file_id, processed_file_id, display_name, metadata_json, price, created_at, photo_url"


async def add_item(
    user_id: int,
    category: str,
    telegram_file_id: str,
    item_type: str | None = None,
    primary_color: str | None = None,
    secondary_color: str | None = None,
    pattern: str | None = None,
    season: str | None = None,
    formality: str | None = None,
    gender_hint: str | None = None,
    processed_file_id: str | None = None,
    display_name: str | None = None,
    price: int = 0,
    photo_url: str | None = None,
) -> int:
    metadata = {
        "type": item_type or "unknown",
        "primary_color": primary_color or "unknown",
        "secondary_color": secondary_color or "unknown",
        "pattern": pattern or "unknown",
        "season": season or "unknown",
        "formality": formality or "unknown",
        "gender_hint": gender_hint or "unknown",
    }

    metadata_json = json.dumps(metadata, ensure_ascii=False)

    if _USE_PG:
        async with _connect() as db:
            row_id = await db.fetchval(
                "INSERT INTO wardrobe_items (user_id, category, telegram_file_id, processed_file_id, display_name, metadata_json, price, photo_url) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id",
                (user_id, category, telegram_file_id, processed_file_id, display_name, metadata_json, price, photo_url),
            )
            return int(row_id)
    else:
        async with _connect() as db:
            await db.execute(
                "INSERT INTO wardrobe_items (user_id, category, telegram_file_id, processed_file_id, display_name, metadata_json, price, photo_url) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, category, telegram_file_id, processed_file_id, display_name, metadata_json, price, photo_url),
            )
            await db.commit()
            return int(db.lastrowid)


def _build_item_payload(row: dict) -> dict[str, str | int | None]:
    metadata = json.loads(row["metadata_json"])
    return {
        "id": row["id"],
        "category": row["category"],
        "telegram_file_id": row["telegram_file_id"],
        "processed_file_id": row.get("processed_file_id"),
        "display_name": row.get("display_name"),
        "price": row.get("price") or 0,
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
        "photo_url": row.get("photo_url"),
        "type": metadata.get("type", "unknown"),
        "primary_color": metadata.get("primary_color", "unknown"),
        "secondary_color": metadata.get("secondary_color", "unknown"),
        "pattern": metadata.get("pattern", "unknown"),
        "season": metadata.get("season", "unknown"),
        "formality": metadata.get("formality", "unknown"),
        "gender_hint": metadata.get("gender_hint", "unknown"),
    }


async def get_items(user_id: int) -> list[dict[str, str | int | None]]:
    async with _connect() as db:
        rows = await db.fetch(
            f"SELECT {_ITEM_COLS} FROM wardrobe_items WHERE user_id = {_ph(1)} ORDER BY id ASC",
            (user_id,),
        )
    return [_build_item_payload(row) for row in rows]


async def delete_item_by_id(user_id: int, item_id: int) -> dict[str, str | int | None] | None:
    async with _connect() as db:
        row = await db.fetchone(
            f"SELECT {_ITEM_COLS} FROM wardrobe_items WHERE id = {_ph(1)} AND user_id = {_ph(2)}",
            (item_id, user_id),
        )
        if not row:
            return None
        await db.execute(
            f"DELETE FROM wardrobe_items WHERE id = {_ph(1)} AND user_id = {_ph(2)}",
            (item_id, user_id),
        )
        await db.commit()
    return _build_item_payload(row)


async def delete_item(user_id: int, item_index: int) -> dict[str, str | int | None] | None:
    if item_index < 0:
        return None
    async with _connect() as db:
        if _USE_PG:
            row = await db.fetchone(
                "SELECT id FROM wardrobe_items WHERE user_id = $1 ORDER BY id ASC LIMIT 1 OFFSET $2",
                (user_id, item_index),
            )
        else:
            row = await db.fetchone(
                "SELECT id FROM wardrobe_items WHERE user_id = ? ORDER BY id ASC LIMIT 1 OFFSET ?",
                (user_id, item_index),
            )
    if not row:
        return None
    return await delete_item_by_id(user_id=user_id, item_id=int(row["id"]))


async def update_processed_file_id(user_id: int, item_id: int, file_id: str) -> bool:
    async with _connect() as db:
        if _USE_PG:
            result = await db._conn.execute(
                "UPDATE wardrobe_items SET processed_file_id = $1 WHERE id = $2 AND user_id = $3",
                file_id, item_id, user_id,
            )
            return result.split()[-1] != "0"
        else:
            await db.execute(
                "UPDATE wardrobe_items SET processed_file_id = ? WHERE id = ? AND user_id = ?",
                (file_id, item_id, user_id),
            )
            await db.commit()
            return db.rowcount > 0


async def update_photo_url(user_id: int, item_id: int, photo_url: str) -> bool:
    async with _connect() as db:
        if _USE_PG:
            result = await db._conn.execute(
                "UPDATE wardrobe_items SET photo_url = $1 WHERE id = $2 AND user_id = $3",
                photo_url, item_id, user_id,
            )
            return result.split()[-1] != "0"
        else:
            await db.execute(
                "UPDATE wardrobe_items SET photo_url = ? WHERE id = ? AND user_id = ?",
                (photo_url, item_id, user_id),
            )
            await db.commit()
            return db.rowcount > 0


async def update_display_name(user_id: int, item_id: int, display_name: str) -> bool:
    name = display_name.strip() or None
    async with _connect() as db:
        if _USE_PG:
            result = await db._conn.execute(
                "UPDATE wardrobe_items SET display_name = $1 WHERE id = $2 AND user_id = $3",
                name, item_id, user_id,
            )
            return result.split()[-1] != "0"
        else:
            await db.execute(
                "UPDATE wardrobe_items SET display_name = ? WHERE id = ? AND user_id = ?",
                (name, item_id, user_id),
            )
            await db.commit()
            return db.rowcount > 0


async def update_item_metadata(user_id: int, item_id: int, metadata: dict[str, str]) -> bool:
    async with _connect() as db:
        row = await db.fetchone(
            f"SELECT metadata_json FROM wardrobe_items WHERE id = {_ph(1)} AND user_id = {_ph(2)}",
            (item_id, user_id),
        )
        if not row:
            return False
        existing = json.loads(row["metadata_json"])
        existing.update(metadata)
        new_json = json.dumps(existing, ensure_ascii=False)
        if _USE_PG:
            result = await db._conn.execute(
                "UPDATE wardrobe_items SET metadata_json = $1 WHERE id = $2 AND user_id = $3",
                new_json, item_id, user_id,
            )
            return result.split()[-1] != "0"
        else:
            await db.execute(
                "UPDATE wardrobe_items SET metadata_json = ? WHERE id = ? AND user_id = ?",
                (new_json, item_id, user_id),
            )
            await db.commit()
            return db.rowcount > 0


async def get_category_counts(user_id: int) -> dict[str, int]:
    async with _connect() as db:
        rows = await db.fetch(
            f"SELECT category, COUNT(*) AS cnt FROM wardrobe_items WHERE user_id = {_ph(1)} GROUP BY category",
            (user_id,),
        )
    return {row["category"]: row["cnt"] for row in rows}


async def add_feedback(user_id: int, text: str, contact: str | None = None) -> int:
    if _USE_PG:
        async with _connect() as db:
            row_id = await db.fetchval(
                "INSERT INTO feedback_messages (user_id, text, contact) VALUES ($1, $2, $3) RETURNING id",
                (user_id, text.strip(), contact),
            )
            return int(row_id)
    else:
        async with _connect() as db:
            await db.execute(
                "INSERT INTO feedback_messages (user_id, text, contact) VALUES (?, ?, ?)",
                (user_id, text.strip(), contact),
            )
            await db.commit()
            return int(db.lastrowid)


async def get_wardrobe_stats(user_id: int) -> dict:
    async with _connect() as db:
        row = await db.fetchone(
            f"SELECT COUNT(*) as total, SUM(price) as total_value FROM wardrobe_items WHERE user_id = {_ph(1)}",
            (user_id,),
        )
        total_items = row["total"] or 0
        total_value = row["total_value"] or 0

        cats = await db.fetch(
            f"SELECT category, COUNT(*) as cnt, SUM(price) as val FROM wardrobe_items WHERE user_id = {_ph(1)} GROUP BY category",
            (user_id,),
        )
        categories = {r["category"]: {"count": r["cnt"], "value": r["val"] or 0} for r in cats}

        expensive = await db.fetchone(
            f"SELECT display_name, price FROM wardrobe_items WHERE user_id = {_ph(1)} AND price > 0 ORDER BY price DESC LIMIT 1",
            (user_id,),
        )

        no_price = await db.fetchone(
            f"SELECT COUNT(*) as cnt FROM wardrobe_items WHERE user_id = {_ph(1)} AND (price IS NULL OR price = 0)",
            (user_id,),
        )

    return {
        "total_items": total_items,
        "total_value": total_value,
        "categories": categories,
        "most_expensive": dict(expensive) if expensive else None,
        "no_price_count": no_price["cnt"],
    }


async def update_item_price(user_id: int, item_id: int, price: int) -> bool:
    async with _connect() as db:
        if _USE_PG:
            result = await db._conn.execute(
                "UPDATE wardrobe_items SET price = $1 WHERE id = $2 AND user_id = $3",
                price, item_id, user_id,
            )
            return result.split()[-1] != "0"
        else:
            await db.execute(
                "UPDATE wardrobe_items SET price = ? WHERE id = ? AND user_id = ?",
                (price, item_id, user_id),
            )
            await db.commit()
            return db.rowcount > 0


async def clear_user_items(user_id: int) -> None:
    async with _connect() as db:
        await db.execute(
            f"DELETE FROM wardrobe_items WHERE user_id = {_ph(1)}", (user_id,),
        )
        await db.commit()


# ─── User Profiles / Location ───────────────────────────────────


async def get_user_location(user_id: int) -> tuple[str, float | None, float | None]:
    async with _connect() as db:
        row = await db.fetchone(
            f"SELECT city, lat, lon FROM user_profiles WHERE user_id = {_ph(1)}", (user_id,),
        )
        if row:
            return (row["city"] or "Москва", row["lat"], row["lon"])
        return ("Москва", None, None)


async def set_user_location(user_id: int, city: str, lat: float | None = None, lon: float | None = None) -> None:
    async with _connect() as db:
        await db.execute(
            f"UPDATE user_profiles SET city = {_ph(1)}, lat = {_ph(2)}, lon = {_ph(3)} WHERE user_id = {_ph(4)}",
            (city, lat, lon, user_id),
        )
        await db.commit()


async def record_paywall_hit(user_id: int) -> None:
    async with _connect() as db:
        await db.execute(
            f"UPDATE user_profiles SET paywall_hit_at = {_ph(1)} WHERE user_id = {_ph(2)}",
            (_now_ts(), user_id),
        )
        await db.commit()


async def get_paywall_followup_users(hours_min: int = 24, hours_max: int = 48) -> list[dict]:
    now = datetime.now(timezone.utc) if _USE_PG else datetime.now()
    cutoff_old = now - timedelta(hours=hours_max)
    cutoff_new = now - timedelta(hours=hours_min)
    if not _USE_PG:
        cutoff_old = cutoff_old.isoformat()
        cutoff_new = cutoff_new.isoformat()
    async with _connect() as db:
        rows = await db.fetch(
            f"""SELECT user_id FROM user_profiles
               WHERE paywall_hit_at BETWEEN {_ph(1)} AND {_ph(2)}
               AND subscription_status != 'active'
               AND paywall_hit_at IS NOT NULL""",
            (cutoff_old, cutoff_new),
        )
        return rows


async def clear_paywall_hit(user_id: int) -> None:
    async with _connect() as db:
        await db.execute(
            f"UPDATE user_profiles SET paywall_hit_at = NULL WHERE user_id = {_ph(1)}", (user_id,),
        )
        await db.commit()


async def set_morning_push(user_id: int, enabled: bool, hour: int = 8) -> None:
    async with _connect() as db:
        await db.execute(
            f"UPDATE user_profiles SET morning_push_enabled = {_ph(1)}, morning_push_hour = {_ph(2)} WHERE user_id = {_ph(3)}",
            (1 if enabled else 0, hour, user_id),
        )
        await db.commit()


async def get_morning_push_users(hour: int) -> list[dict]:
    async with _connect() as db:
        rows = await db.fetch(
            f"""SELECT user_id, city, lat, lon FROM user_profiles
               WHERE morning_push_enabled = 1 AND morning_push_hour = {_ph(1)}
               AND subscription_status = 'active'""",
            (hour,),
        )
        return rows


# ─── Outfit History ─────────────────────────────────────────────


async def save_outfit_to_history(
    user_id: int,
    item_file_ids: list[str],
    occasion: str,
    season: str,
) -> None:
    async with _connect() as db:
        await db.execute(
            f"INSERT INTO outfit_history (user_id, outfit_items, occasion, season) "
            f"VALUES ({_ph(1)}, {_ph(2)}, {_ph(3)}, {_ph(4)})",
            (user_id, json.dumps(item_file_ids), occasion, season),
        )
        await db.commit()


async def get_outfit_history(user_id: int, days: int = 7) -> list[dict]:
    if _USE_PG:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        sql = (
            "SELECT outfit_items, occasion, season, liked, created_at "
            "FROM outfit_history WHERE user_id = $1 "
            "AND created_at >= $2 "
            "ORDER BY created_at DESC"
        )
    else:
        cutoff = f"-{days} days"
        sql = (
            "SELECT outfit_items, occasion, season, liked, created_at "
            "FROM outfit_history WHERE user_id = ? "
            "AND created_at >= datetime('now', ?) "
            "ORDER BY created_at DESC"
        )

    async with _connect() as db:
        rows = await db.fetch(sql, (user_id, cutoff))

    result = []
    for row in rows:
        d = dict(row)
        d["outfit_items"] = json.loads(d["outfit_items"])
        if d.get("created_at"):
            d["created_at"] = str(d["created_at"])
        result.append(d)
    return result


async def get_recent_outfit_item_ids(user_id: int, days: int = 3) -> set[str]:
    history = await get_outfit_history(user_id, days=days)
    used: set[str] = set()
    for entry in history:
        used.update(entry["outfit_items"])
    return used


# ─── Survey ─────────────────────────────────────────────────


async def save_survey_feedback(
    user_id: int,
    rating: int | None,
    most_valuable: str | None,
    free_text: str | None,
) -> None:
    async with _connect() as db:
        await db.execute(
            f"INSERT INTO survey_feedback (user_id, rating, most_valuable, free_text) "
            f"VALUES ({_ph(1)}, {_ph(2)}, {_ph(3)}, {_ph(4)})",
            (user_id, rating, most_valuable, free_text),
        )
        await db.commit()


async def should_show_survey(user_id: int, days: int = 7) -> bool:
    async with _connect() as db:
        row = await db.fetchone(
            f"SELECT survey_shown_at FROM user_profiles WHERE user_id = {_ph(1)}", (user_id,),
        )
    if not row or row["survey_shown_at"] is None:
        return True
    from datetime import datetime as _dt
    try:
        val = row["survey_shown_at"]
        shown = _dt.fromisoformat(str(val)) if not isinstance(val, _dt) else val
        delta = (_dt.now() - shown.replace(tzinfo=None)).total_seconds()
        return delta > days * 86400
    except Exception:
        return True


async def update_survey_shown_at(user_id: int) -> None:
    async with _connect() as db:
        await db.execute(
            f"UPDATE user_profiles SET survey_shown_at = {_ph(1)} WHERE user_id = {_ph(2)}",
            (_now_ts(), user_id),
        )
        await db.commit()


async def is_first_start(user_id: int) -> bool:
    async with _connect() as db:
        row = await db.fetchone(
            f"SELECT created_at FROM user_profiles WHERE user_id = {_ph(1)}", (user_id,),
        )
    if not row:
        return False
    from datetime import datetime as _dt
    try:
        val = row["created_at"]
        created = _dt.fromisoformat(str(val)) if not isinstance(val, _dt) else val
        now = _dt.now()
        delta = (now - created.replace(tzinfo=None)).total_seconds()
        return delta < 300
    except Exception:
        return False


# ─── Daily Stats ─────────────────────────────────────────────


_ALLOWED_STATS = {"new_subscriptions", "errors_count"}


async def increment_daily_stat(stat_name: str) -> None:
    if stat_name not in _ALLOWED_STATS:
        return
    if _USE_PG:
        sql = (
            f"INSERT INTO daily_stats (date, {stat_name}) "
            f"VALUES (CURRENT_DATE::TEXT, 1) "
            f"ON CONFLICT(date) DO UPDATE SET {stat_name} = daily_stats.{stat_name} + 1"
        )
    else:
        sql = (
            f"INSERT INTO daily_stats (date, {stat_name}) "
            f"VALUES (date('now'), 1) "
            f"ON CONFLICT(date) DO UPDATE SET {stat_name} = {stat_name} + 1"
        )
    async with _connect() as db:
        await db.execute(sql)
        await db.commit()


async def get_stats_for_daily_report() -> dict:
    if _USE_PG:
        date_expr = "CURRENT_DATE::TEXT"
        date_cmp = "created_at::DATE = CURRENT_DATE"
    else:
        date_expr = "date('now')"
        date_cmp = "date(created_at) = date('now')"

    async with _connect() as db:
        new_users = (await db.fetchone(
            f"SELECT COUNT(*) as cnt FROM user_profiles WHERE {date_cmp}"
        )) or {}
        new_users = new_users.get("cnt") or 0

        total_users = (await db.fetchone(
            "SELECT COUNT(*) as cnt FROM user_profiles"
        )) or {}
        total_users = total_users.get("cnt") or 0

        items_uploaded = (await db.fetchone(
            f"SELECT COUNT(*) as cnt FROM wardrobe_items WHERE {date_cmp}"
        )) or {}
        items_uploaded = items_uploaded.get("cnt") or 0

        outfit_requests = (await db.fetchone(
            f"SELECT COUNT(*) as cnt FROM outfit_history WHERE {date_cmp}"
        )) or {}
        outfit_requests = outfit_requests.get("cnt") or 0

        today_row = await db.fetchone(
            f"SELECT new_subscriptions, errors_count FROM daily_stats WHERE date = {date_expr}"
        )

    return {
        "new_users": new_users,
        "total_users": total_users,
        "items_uploaded": items_uploaded,
        "outfit_requests": outfit_requests,
        "new_subscriptions": today_row["new_subscriptions"] if today_row else 0,
        "errors_count": today_row["errors_count"] if today_row else 0,
    }
