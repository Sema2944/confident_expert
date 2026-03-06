from __future__ import annotations

import json
import os
from pathlib import Path

import aiosqlite
from contextlib import asynccontextmanager

_STORAGE_PATH = Path(os.getenv("WARDROBE_STORAGE_PATH", Path(__file__).resolve().parents[1] / "data" / "wardrobe.sqlite3"))
_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def _connect():
    async with aiosqlite.connect(_STORAGE_PATH) as connection:
        connection.row_factory = aiosqlite.Row
        yield connection


async def init_storage() -> None:
    async with _connect() as connection:
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
        # Миграция: координаты + конверсия + push
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

        # Миграция: survey_shown_at для user_profiles
        if "survey_shown_at" not in user_cols:
            await connection.execute("ALTER TABLE user_profiles ADD COLUMN survey_shown_at DATETIME")

        await connection.commit()


async def log_outfit_feedback(
    user_id: int, occasion: str, season: str, action: str, items: dict,
) -> None:
    import json as _json
    async with _connect() as connection:
        await connection.execute(
            """
            INSERT INTO outfit_feedback (user_id, occasion, season, action, items_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, occasion, season, action, _json.dumps(items, ensure_ascii=False)),
        )
        await connection.commit()


async def get_liked_items(user_id: int) -> list[str]:
    """Возвращает file_id вещей из liked-образов."""
    import json as _json
    async with _connect() as connection:
        cursor = await connection.execute(
            """
            SELECT items_json FROM outfit_feedback
            WHERE user_id = ? AND action = 'like'
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()

    file_ids: list[str] = []
    for row in rows:
        items = _json.loads(row["items_json"])
        for fids in items.values():
            if isinstance(fids, list):
                file_ids.extend(fids)
    return file_ids


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

    async with _connect() as connection:
        cursor = await connection.execute(
            """
            INSERT INTO wardrobe_items (
                user_id,
                category,
                telegram_file_id,
                processed_file_id,
                display_name,
                metadata_json,
                price,
                photo_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                category,
                telegram_file_id,
                processed_file_id,
                display_name,
                json.dumps(metadata, ensure_ascii=False),
                price,
                photo_url,
            ),
        )
        await connection.commit()
        return int(cursor.lastrowid)


def _build_item_payload(row: aiosqlite.Row) -> dict[str, str | int | None]:
    metadata = json.loads(row["metadata_json"])
    try:
        price = row["price"] or 0
    except Exception:
        price = 0
    try:
        created_at = row["created_at"]
    except Exception:
        created_at = None
    try:
        photo_url = row["photo_url"]
    except Exception:
        photo_url = None
    return {
        "id": row["id"],
        "category": row["category"],
        "telegram_file_id": row["telegram_file_id"],
        "processed_file_id": row["processed_file_id"],
        "display_name": row["display_name"],
        "price": price,
        "created_at": created_at,
        "photo_url": photo_url,
        "type": metadata.get("type", "unknown"),
        "primary_color": metadata.get("primary_color", "unknown"),
        "secondary_color": metadata.get("secondary_color", "unknown"),
        "pattern": metadata.get("pattern", "unknown"),
        "season": metadata.get("season", "unknown"),
        "formality": metadata.get("formality", "unknown"),
        "gender_hint": metadata.get("gender_hint", "unknown"),
    }


async def get_items(user_id: int) -> list[dict[str, str | int | None]]:
    async with _connect() as connection:
        cursor = await connection.execute(
            """
            SELECT id, category, telegram_file_id, processed_file_id, display_name, metadata_json, price, created_at, photo_url
            FROM wardrobe_items
            WHERE user_id = ?
            ORDER BY id ASC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()

    return [_build_item_payload(row) for row in rows]


async def delete_item_by_id(user_id: int, item_id: int) -> dict[str, str | int | None] | None:
    async with _connect() as connection:
        cursor = await connection.execute(
            """
            SELECT id, category, telegram_file_id, processed_file_id, display_name, metadata_json, price, created_at, photo_url
            FROM wardrobe_items
            WHERE id = ? AND user_id = ?
            """,
            (item_id, user_id),
        )
        row = await cursor.fetchone()

        if not row:
            return None

        await connection.execute("DELETE FROM wardrobe_items WHERE id = ? AND user_id = ?", (item_id, user_id))
        await connection.commit()

    return _build_item_payload(row)


async def delete_item(user_id: int, item_index: int) -> dict[str, str | int | None] | None:
    """Backward-compatible deletion by list index."""
    if item_index < 0:
        return None

    async with _connect() as connection:
        cursor = await connection.execute(
            """
            SELECT id
            FROM wardrobe_items
            WHERE user_id = ?
            ORDER BY id ASC
            LIMIT 1 OFFSET ?
            """,
            (user_id, item_index),
        )
        row = await cursor.fetchone()

    if not row:
        return None

    return await delete_item_by_id(user_id=user_id, item_id=int(row["id"]))


async def update_processed_file_id(user_id: int, item_id: int, file_id: str) -> bool:
    async with _connect() as connection:
        cursor = await connection.execute(
            """
            UPDATE wardrobe_items
            SET processed_file_id = ?
            WHERE id = ? AND user_id = ?
            """,
            (file_id, item_id, user_id),
        )
        await connection.commit()
    return cursor.rowcount > 0


async def update_photo_url(user_id: int, item_id: int, photo_url: str) -> bool:
    async with _connect() as connection:
        cursor = await connection.execute(
            """
            UPDATE wardrobe_items
            SET photo_url = ?
            WHERE id = ? AND user_id = ?
            """,
            (photo_url, item_id, user_id),
        )
        await connection.commit()
    return cursor.rowcount > 0


async def update_display_name(user_id: int, item_id: int, display_name: str) -> bool:
    async with _connect() as connection:
        cursor = await connection.execute(
            """
            UPDATE wardrobe_items
            SET display_name = ?
            WHERE id = ? AND user_id = ?
            """,
            (display_name.strip() or None, item_id, user_id),
        )
        await connection.commit()
    return cursor.rowcount > 0


async def update_item_metadata(user_id: int, item_id: int, metadata: dict[str, str]) -> bool:
    async with _connect() as connection:
        cursor = await connection.execute(
            """
            SELECT metadata_json
            FROM wardrobe_items
            WHERE id = ? AND user_id = ?
            """,
            (item_id, user_id),
        )
        row = await cursor.fetchone()
        if not row:
            return False

        existing = json.loads(row["metadata_json"])
        existing.update(metadata)
        cursor = await connection.execute(
            """
            UPDATE wardrobe_items
            SET metadata_json = ?
            WHERE id = ? AND user_id = ?
            """,
            (json.dumps(existing, ensure_ascii=False), item_id, user_id),
        )
        await connection.commit()
    return cursor.rowcount > 0


async def get_category_counts(user_id: int) -> dict[str, int]:
    async with _connect() as connection:
        cursor = await connection.execute(
            """
            SELECT category, COUNT(*) AS cnt
            FROM wardrobe_items
            WHERE user_id = ?
            GROUP BY category
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
    return {row["category"]: row["cnt"] for row in rows}


async def add_feedback(user_id: int, text: str, contact: str | None = None) -> int:
    async with _connect() as connection:
        cursor = await connection.execute(
            """
            INSERT INTO feedback_messages (user_id, text, contact)
            VALUES (?, ?, ?)
            """,
            (user_id, text.strip(), contact),
        )
        await connection.commit()
        return int(cursor.lastrowid)


async def get_wardrobe_stats(user_id: int) -> dict:
    async with _connect() as connection:
        row = await (await connection.execute(
            "SELECT COUNT(*) as total, SUM(price) as total_value FROM wardrobe_items WHERE user_id = ?",
            (user_id,),
        )).fetchone()
        total_items = row["total"] or 0
        total_value = row["total_value"] or 0

        cats = await (await connection.execute(
            "SELECT category, COUNT(*) as cnt, SUM(price) as val FROM wardrobe_items WHERE user_id = ? GROUP BY category",
            (user_id,),
        )).fetchall()
        categories = {r["category"]: {"count": r["cnt"], "value": r["val"] or 0} for r in cats}

        expensive = await (await connection.execute(
            "SELECT display_name, price FROM wardrobe_items WHERE user_id = ? AND price > 0 ORDER BY price DESC LIMIT 1",
            (user_id,),
        )).fetchone()

        no_price = await (await connection.execute(
            "SELECT COUNT(*) as cnt FROM wardrobe_items WHERE user_id = ? AND (price IS NULL OR price = 0)",
            (user_id,),
        )).fetchone()

    return {
        "total_items": total_items,
        "total_value": total_value,
        "categories": categories,
        "most_expensive": dict(expensive) if expensive else None,
        "no_price_count": no_price["cnt"],
    }


async def update_item_price(user_id: int, item_id: int, price: int) -> bool:
    async with _connect() as connection:
        cursor = await connection.execute(
            "UPDATE wardrobe_items SET price = ? WHERE id = ? AND user_id = ?",
            (price, item_id, user_id),
        )
        await connection.commit()
    return cursor.rowcount > 0


async def clear_user_items(user_id: int) -> None:
    async with _connect() as connection:
        await connection.execute("DELETE FROM wardrobe_items WHERE user_id = ?", (user_id,))
        await connection.commit()


async def get_user_location(user_id: int) -> tuple[str, float | None, float | None]:
    """Возвращает (city, lat, lon). Город по умолчанию 'Москва'."""
    async with _connect() as connection:
        row = await (await connection.execute(
            "SELECT city, lat, lon FROM user_profiles WHERE user_id = ?", (user_id,),
        )).fetchone()
        if row:
            return (row["city"] or "Москва", row["lat"], row["lon"])
        return ("Москва", None, None)


async def set_user_location(user_id: int, city: str, lat: float | None = None, lon: float | None = None) -> None:
    async with _connect() as connection:
        await connection.execute(
            "UPDATE user_profiles SET city = ?, lat = ?, lon = ? WHERE user_id = ?",
            (city, lat, lon, user_id),
        )
        await connection.commit()


async def record_paywall_hit(user_id: int) -> None:
    """Фиксировать момент упёртости в paywall для follow-up."""
    from datetime import datetime as _dt
    async with _connect() as connection:
        await connection.execute(
            "UPDATE user_profiles SET paywall_hit_at = ? WHERE user_id = ?",
            (_dt.now().isoformat(), user_id),
        )
        await connection.commit()


async def get_paywall_followup_users(hours_min: int = 24, hours_max: int = 48) -> list[dict]:
    """Пользователи, которые упёрлись в paywall hours_min–hours_max часов назад и не оплатили."""
    from datetime import datetime as _dt, timedelta as _td
    cutoff_old = (_dt.now() - _td(hours=hours_max)).isoformat()
    cutoff_new = (_dt.now() - _td(hours=hours_min)).isoformat()
    async with _connect() as connection:
        rows = await (await connection.execute(
            """SELECT user_id FROM user_profiles
               WHERE paywall_hit_at BETWEEN ? AND ?
               AND subscription_status != 'active'
               AND paywall_hit_at IS NOT NULL""",
            (cutoff_old, cutoff_new),
        )).fetchall()
        return [dict(r) for r in rows]


async def clear_paywall_hit(user_id: int) -> None:
    async with _connect() as connection:
        await connection.execute(
            "UPDATE user_profiles SET paywall_hit_at = NULL WHERE user_id = ?", (user_id,),
        )
        await connection.commit()


async def set_morning_push(user_id: int, enabled: bool, hour: int = 8) -> None:
    async with _connect() as connection:
        await connection.execute(
            "UPDATE user_profiles SET morning_push_enabled = ?, morning_push_hour = ? WHERE user_id = ?",
            (1 if enabled else 0, hour, user_id),
        )
        await connection.commit()


async def get_morning_push_users(hour: int) -> list[dict]:
    """Подписчики с активным morning push на указанный час."""
    async with _connect() as connection:
        rows = await (await connection.execute(
            """SELECT user_id, city, lat, lon FROM user_profiles
               WHERE morning_push_enabled = 1 AND morning_push_hour = ?
               AND subscription_status = 'active'""",
            (hour,),
        )).fetchall()
        return [dict(r) for r in rows]


# ─── Outfit History ─────────────────────────────────────────────


async def save_outfit_to_history(
    user_id: int,
    item_file_ids: list[str],
    occasion: str,
    season: str,
) -> None:
    async with _connect() as connection:
        await connection.execute(
            "INSERT INTO outfit_history (user_id, outfit_items, occasion, season) VALUES (?, ?, ?, ?)",
            (user_id, json.dumps(item_file_ids), occasion, season),
        )
        await connection.commit()


async def get_outfit_history(user_id: int, days: int = 7) -> list[dict]:
    async with _connect() as connection:
        rows = await (await connection.execute(
            """SELECT outfit_items, occasion, season, liked, created_at
               FROM outfit_history WHERE user_id = ?
               AND created_at >= datetime('now', ?)
               ORDER BY created_at DESC""",
            (user_id, f"-{days} days"),
        )).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["outfit_items"] = json.loads(d["outfit_items"])
        result.append(d)
    return result


async def get_recent_outfit_item_ids(user_id: int, days: int = 3) -> set[str]:
    """Вещи, использованные в образах за последние N дней."""
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
    async with _connect() as connection:
        await connection.execute(
            "INSERT INTO survey_feedback (user_id, rating, most_valuable, free_text) VALUES (?, ?, ?, ?)",
            (user_id, rating, most_valuable, free_text),
        )
        await connection.commit()


async def should_show_survey(user_id: int, days: int = 7) -> bool:
    """True если опрос не показывался пользователю последние N дней."""
    async with _connect() as connection:
        row = await (await connection.execute(
            "SELECT survey_shown_at FROM user_profiles WHERE user_id = ?", (user_id,),
        )).fetchone()
    if not row or row["survey_shown_at"] is None:
        return True
    from datetime import datetime as _dt
    try:
        shown = _dt.fromisoformat(row["survey_shown_at"])
        delta = (_dt.now() - shown).total_seconds()
        return delta > days * 86400
    except Exception:
        return True


async def update_survey_shown_at(user_id: int) -> None:
    from datetime import datetime as _dt
    async with _connect() as connection:
        await connection.execute(
            "UPDATE user_profiles SET survey_shown_at = ? WHERE user_id = ?",
            (_dt.now().isoformat(), user_id),
        )
        await connection.commit()


async def is_first_start(user_id: int) -> bool:
    """True если пользователь создан менее 5 минут назад."""
    async with _connect() as connection:
        row = await (await connection.execute(
            "SELECT created_at FROM user_profiles WHERE user_id = ?", (user_id,),
        )).fetchone()
    if not row:
        return False
    from datetime import datetime as _dt, timezone as _tz
    try:
        created = _dt.fromisoformat(row["created_at"])
        # SQLite CURRENT_TIMESTAMP is UTC without tzinfo
        now = _dt.now()
        delta = (now - created).total_seconds()
        return delta < 300
    except Exception:
        return False


# ─── Daily Stats ─────────────────────────────────────────────


_ALLOWED_STATS = {"new_subscriptions", "errors_count"}


async def increment_daily_stat(stat_name: str) -> None:
    if stat_name not in _ALLOWED_STATS:
        return
    async with _connect() as connection:
        await connection.execute(
            f"""
            INSERT INTO daily_stats (date, {stat_name})
            VALUES (date('now'), 1)
            ON CONFLICT(date) DO UPDATE SET {stat_name} = {stat_name} + 1
            """,
        )
        await connection.commit()


async def get_stats_for_daily_report() -> dict:
    async with _connect() as connection:
        new_users = (await (await connection.execute(
            "SELECT COUNT(*) as cnt FROM user_profiles WHERE date(created_at) = date('now')"
        )).fetchone())["cnt"] or 0

        total_users = (await (await connection.execute(
            "SELECT COUNT(*) as cnt FROM user_profiles"
        )).fetchone())["cnt"] or 0

        items_uploaded = (await (await connection.execute(
            "SELECT COUNT(*) as cnt FROM wardrobe_items WHERE date(created_at) = date('now')"
        )).fetchone())["cnt"] or 0

        outfit_requests = (await (await connection.execute(
            "SELECT COUNT(*) as cnt FROM outfit_history WHERE date(created_at) = date('now')"
        )).fetchone())["cnt"] or 0

        today_row = await (await connection.execute(
            "SELECT new_subscriptions, errors_count FROM daily_stats WHERE date = date('now')"
        )).fetchone()

    return {
        "new_users": new_users,
        "total_users": total_users,
        "items_uploaded": items_uploaded,
        "outfit_requests": outfit_requests,
        "new_subscriptions": today_row["new_subscriptions"] if today_row else 0,
        "errors_count": today_row["errors_count"] if today_row else 0,
    }
