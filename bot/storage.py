from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

_STORAGE_PATH = Path(os.getenv("WARDROBE_STORAGE_PATH", Path(__file__).resolve().parents[1] / "data" / "wardrobe.sqlite3"))
_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_STORAGE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _init_storage() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS wardrobe_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                telegram_file_id TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
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


_init_storage()


def add_item(
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
) -> None:
    metadata = {
        "type": item_type or "unknown",
        "primary_color": primary_color or "unknown",
        "secondary_color": secondary_color or "unknown",
        "pattern": pattern or "unknown",
        "season": season or "unknown",
        "formality": formality or "unknown",
        "gender_hint": gender_hint or "unknown",
    }

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO wardrobe_items (user_id, category, telegram_file_id, metadata_json)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, category, telegram_file_id, json.dumps(metadata, ensure_ascii=False)),
        )


def get_items(user_id: int) -> list[dict[str, str]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT category, telegram_file_id, metadata_json
            FROM wardrobe_items
            WHERE user_id = ?
            ORDER BY id ASC
            """,
            (user_id,),
        ).fetchall()

    items: list[dict[str, str]] = []
    for row in rows:
        metadata = json.loads(row["metadata_json"])
        items.append(
            {
                "category": row["category"],
                "telegram_file_id": row["telegram_file_id"],
                "type": metadata.get("type", "unknown"),
                "primary_color": metadata.get("primary_color", "unknown"),
                "secondary_color": metadata.get("secondary_color", "unknown"),
                "pattern": metadata.get("pattern", "unknown"),
                "season": metadata.get("season", "unknown"),
                "formality": metadata.get("formality", "unknown"),
                "gender_hint": metadata.get("gender_hint", "unknown"),
            }
        )
    return items


def delete_item(user_id: int, item_index: int) -> dict[str, str] | None:
    if item_index < 0:
        return None

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT id, category, telegram_file_id, metadata_json
            FROM wardrobe_items
            WHERE user_id = ?
            ORDER BY id ASC
            LIMIT 1 OFFSET ?
            """,
            (user_id, item_index),
        ).fetchone()

        if not row:
            return None

        connection.execute("DELETE FROM wardrobe_items WHERE id = ?", (row["id"],))

    metadata = json.loads(row["metadata_json"])
    return {
        "category": row["category"],
        "telegram_file_id": row["telegram_file_id"],
        "type": metadata.get("type", "unknown"),
        "primary_color": metadata.get("primary_color", "unknown"),
        "secondary_color": metadata.get("secondary_color", "unknown"),
        "pattern": metadata.get("pattern", "unknown"),
        "season": metadata.get("season", "unknown"),
        "formality": metadata.get("formality", "unknown"),
        "gender_hint": metadata.get("gender_hint", "unknown"),
    }


def get_category_counts(user_id: int) -> dict[str, int]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT category, COUNT(*) AS cnt
            FROM wardrobe_items
            WHERE user_id = ?
            GROUP BY category
            """,
            (user_id,),
        ).fetchall()
    return {row["category"]: row["cnt"] for row in rows}


def add_feedback(user_id: int, text: str, contact: str | None = None) -> int:
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO feedback_messages (user_id, text, contact)
            VALUES (?, ?, ?)
            """,
            (user_id, text.strip(), contact),
        )
        return int(cursor.lastrowid)


def clear_user_items(user_id: int) -> None:
    with _connect() as connection:
        connection.execute("DELETE FROM wardrobe_items WHERE user_id = ?", (user_id,))
