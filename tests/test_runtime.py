import asyncio
import sqlite3
import unittest

from pydantic import ValidationError

from bot.runtime import (
    build_fsm_storage,
    fsm_storage_label,
    normalize_tg_mode,
    resolve_database_url,
    storage_backend_label,
)
from config.settings import Settings
from scripts.sqlite_to_postgres import TABLE_KEYS, build_upsert_sql, copy_table_sqlite


class RuntimeChoiceTests(unittest.TestCase):
    def test_database_url_is_used_when_db_url_empty(self) -> None:
        self.assertEqual(
            resolve_database_url("", "postgresql://wardrobe:secret@db:5432/wardrobe"),
            "postgresql://wardrobe:secret@db:5432/wardrobe",
        )
        self.assertEqual(
            resolve_database_url("postgresql://explicit/db", "postgresql://other/db"),
            "postgresql://explicit/db",
        )
        self.assertEqual(resolve_database_url(None, None), "")

    def test_postgres_label_hides_password(self) -> None:
        label = storage_backend_label(
            "postgresql://wardrobe:super-secret@postgres:5432/wardrobe"
        )
        self.assertIn("PostgreSQL", label)
        self.assertIn("host=postgres", label)
        self.assertIn("port=5432", label)
        self.assertIn("dbname=wardrobe", label)
        self.assertIn("user=wardrobe", label)
        self.assertNotIn("super-secret", label)
        self.assertNotIn("://", label)

    def test_sqlite_label_when_url_missing(self) -> None:
        label = storage_backend_label("", "/data/wardrobe.sqlite3")
        self.assertEqual(label, "SQLite (/data/wardrobe.sqlite3)")

    def test_tg_mode_defaults_to_webhook(self) -> None:
        self.assertEqual(normalize_tg_mode(None), "webhook")
        self.assertEqual(normalize_tg_mode("  Polling "), "polling")
        with self.assertRaises(ValueError):
            normalize_tg_mode("both")

    def test_settings_accepts_database_url_and_polling(self) -> None:
        settings = Settings(
            bot_token="123456:TEST",
            db_url="",
            database_url="postgresql://wardrobe:super-secret@postgres:5432/wardrobe",
            tg_mode="polling",
        )
        self.assertEqual(settings.tg_mode, "polling")
        self.assertTrue(settings.db_url.startswith("postgresql://wardrobe:"))
        self.assertNotIn("super-secret", storage_backend_label(settings.db_url))
        with self.assertRaises(ValidationError):
            Settings(bot_token="123456:TEST", tg_mode="socket")

    def test_fsm_defaults_to_memory_and_redis_label_hides_password(self) -> None:
        storage = build_fsm_storage(None)
        self.assertEqual(type(storage).__name__, "MemoryStorage")
        self.assertEqual(build_fsm_storage("  ").__class__.__name__, "MemoryStorage")
        label = fsm_storage_label("redis://:super-secret@redis.internal:6379/2")
        self.assertIn("Redis", label)
        self.assertIn("host=redis.internal", label)
        self.assertNotIn("super-secret", label)

    def test_redis_url_selects_redis_storage(self) -> None:
        storage = build_fsm_storage("redis://localhost:6379/0")
        self.assertEqual(type(storage).__name__, "RedisStorage")
        asyncio.run(storage.close())


class SqliteCopyTests(unittest.TestCase):
    def test_copy_is_idempotent_and_does_not_overwrite(self) -> None:
        src = sqlite3.connect(":memory:")
        dest = sqlite3.connect(":memory:")
        for conn in (src, dest):
            conn.execute(
                "CREATE TABLE user_profiles (user_id INTEGER PRIMARY KEY, username TEXT)"
            )
        src.execute("INSERT INTO user_profiles (user_id, username) VALUES (1, 'anna')")
        src.commit()
        first = copy_table_sqlite(src, dest, "user_profiles")
        src.execute("UPDATE user_profiles SET username = 'other' WHERE user_id = 1")
        src.commit()
        second = copy_table_sqlite(src, dest, "user_profiles")
        kept = dest.execute("SELECT username FROM user_profiles WHERE user_id = 1").fetchone()[0]
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(kept, "anna")
        sql = build_upsert_sql("user_profiles", ["user_id", "username"], TABLE_KEYS["user_profiles"], dollar=True)
        self.assertIn("ON CONFLICT (user_id) DO NOTHING", sql)
        self.assertIn("$1", sql)
        src.close()
        dest.close()


class ComposeFileTests(unittest.TestCase):
    def test_compose_is_v1_compatible_and_does_not_publish_postgres(self) -> None:
        from pathlib import Path

        text = Path("docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn('version: "2.4"', text)
        self.assertIn("mem_limit:", text)
        self.assertNotIn("deploy:", text)
        self.assertIn("container_name: shkaf-postgres", text)
        self.assertIn("container_name: shkaf-bot", text)
        self.assertIn("127.0.0.1:${HOST_PORT:-8095}:${PORT:-10000}", text)
        self.assertNotIn("5432:5432", text)
        self.assertNotIn("0.0.0.0:5432", text)
        postgres = text.split("services:", 1)[1].split("bot:", 1)[0]
        self.assertNotIn("ports:", postgres)


if __name__ == "__main__":
    unittest.main()
