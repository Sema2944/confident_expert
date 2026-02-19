from __future__ import annotations

import json
import os
from pathlib import Path

import aiosqlite

_STORAGE_PATH = Path(os.getenv("WARDROBE_STORAGE_PATH", Path(__file__).resolve().parents[1] / "data" / "wardrobe.sqlite3"))
_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)


async def _connect() -> aiosqlite.Connection:
    connection = await aiosqlite.connect(_STORAGE_PATH)
    connection.row_factory = aiosqlite.Row
    return connection


async def init_storage() -> None:
    async with await _connect() as connection:
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
        await connection.commit()


async def log_outfit_feedback(
    user_id: int, occasion: str, season: str, action: str, items: dict,
) -> None:
    import json as _json
    async with await _connect() as connection:
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
    async with await _connect() as connection:
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

    async with await _connect() as connection:
        cursor = await connection.execute(
            """
            INSERT INTO wardrobe_items (
                user_id,
                category,
                telegram_file_id,
                processed_file_id,
                display_name,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                category,
                telegram_file_id,
                processed_file_id,
                display_name,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
        await connection.commit()
        return int(cursor.lastrowid)


def _build_item_payload(row: aiosqlite.Row) -> dict[str, str | int | None]:
    metadata = json.loads(row["metadata_json"])
    return {
        "id": row["id"],
        "category": row["category"],
        "telegram_file_id": row["telegram_file_id"],
        "processed_file_id": row["processed_file_id"],
        "display_name": row["display_name"],
        "type": metadata.get("type", "unknown"),
        "primary_color": metadata.get("primary_color", "unknown"),
        "secondary_color": metadata.get("secondary_color", "unknown"),
        "pattern": metadata.get("pattern", "unknown"),
        "season": metadata.get("season", "unknown"),
        "formality": metadata.get("formality", "unknown"),
        "gender_hint": metadata.get("gender_hint", "unknown"),
    }


async def get_items(user_id: int) -> list[dict[str, str | int | None]]:
    async with await _connect() as connection:
        cursor = await connection.execute(
            """
            SELECT id, category, telegram_file_id, processed_file_id, display_name, metadata_json
            FROM wardrobe_items
            WHERE user_id = ?
            ORDER BY id ASC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()

    return [_build_item_payload(row) for row in rows]


async def delete_item_by_id(user_id: int, item_id: int) -> dict[str, str | int | None] | None:
    async with await _connect() as connection:
        cursor = await connection.execute(
            """
            SELECT id, category, telegram_file_id, processed_file_id, display_name, metadata_json
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

    async with await _connect() as connection:
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
    async with await _connect() as connection:
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


async def update_display_name(user_id: int, item_id: int, display_name: str) -> bool:
    async with await _connect() as connection:
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
    async with await _connect() as connection:
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
    async with await _connect() as connection:
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
    async with await _connect() as connection:
        cursor = await connection.execute(
            """
            INSERT INTO feedback_messages (user_id, text, contact)
            VALUES (?, ?, ?)
            """,
            (user_id, text.strip(), contact),
        )
        await connection.commit()
        return int(cursor.lastrowid)


async def clear_user_items(user_id: int) -> None:
    async with await _connect() as connection:
        await connection.execute("DELETE FROM wardrobe_items WHERE user_id = ?", (user_id,))
        await connection.commit()
