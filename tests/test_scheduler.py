import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bot import storage
from bot.scheduler import (
    WEEK1_POSTS,
    WEEK2_POSTS,
    _is_stale,
    _seed_posts,
    init_scheduled_posts_table,
    process_due_posts,
    seed_week1_posts,
    seed_week2_posts,
    start_channel_autopost,
)
from bot.storage import _connect, _ph
from config.settings import Settings


def _texts(bot: AsyncMock) -> list[str]:
    found = []
    for call in bot.send_message.call_args_list:
        if "text" in call.kwargs:
            found.append(call.kwargs["text"])
        elif len(call.args) > 1:
            found.append(call.args[1])
    return found


def _questions(bot: AsyncMock) -> list[str]:
    found = []
    for call in bot.send_poll.call_args_list:
        if "question" in call.kwargs:
            found.append(call.kwargs["question"])
        elif len(call.args) > 1:
            found.append(call.args[1])
    return found


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._prev_path = storage._STORAGE_PATH
        storage._STORAGE_PATH = Path(self._tmpdir.name) / "wardrobe.sqlite3"
        self.assertFalse(storage._USE_PG)
        await init_scheduled_posts_table()

    async def asyncTearDown(self) -> None:
        storage._STORAGE_PATH = self._prev_path
        self._tmpdir.cleanup()

    async def _rows(self, scheduled_at: str) -> list[dict]:
        async with _connect() as db:
            return await db.fetch(
                f"""
                SELECT id, status, sent_at, text_content, poll_question, scheduled_at
                FROM scheduled_posts
                WHERE scheduled_at = {_ph(1)}
                """,
                (scheduled_at,),
            )

    async def _all(self) -> list[dict]:
        async with _connect() as db:
            return await db.fetch(
                """
                SELECT id, status, sent_at, text_content, poll_question, scheduled_at
                FROM scheduled_posts
                ORDER BY id
                """
            )

    async def _insert(
        self,
        *,
        scheduled_at: str,
        status: str,
        text: str,
        sent_at: str | None = None,
    ) -> None:
        async with _connect() as db:
            await db.execute(
                f"""
                INSERT INTO scheduled_posts
                    (scheduled_at, post_type, text_content, channel_id, status, sent_at)
                VALUES ({_ph(1)}, {_ph(2)}, {_ph(3)}, {_ph(4)}, {_ph(5)}, {_ph(6)})
                """,
                (scheduled_at, "text", text, "@shkaf_rabotaet", status, sent_at),
            )
            await db.commit()

    async def test_reseed_does_not_resend_sent_posts(self) -> None:
        catalog = WEEK1_POSTS[0]
        sent_at = "2026-02-24T06:05:00+00:00"
        await self._insert(
            scheduled_at=catalog["scheduled_at"],
            status="sent",
            text="ALREADY_SENT_BODY",
            sent_at=sent_at,
        )

        await seed_week1_posts()
        await seed_week1_posts()

        kept = await self._rows(catalog["scheduled_at"])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["status"], "sent")
        self.assertEqual(kept[0]["sent_at"], sent_at)
        self.assertEqual(kept[0]["text_content"], "ALREADY_SENT_BODY")

        recent_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        recent = {
            "scheduled_at": recent_at,
            "post_type": "text",
            "text_content": "RECENT_BODY",
        }
        await _seed_posts([recent], "grace")
        bot = AsyncMock()
        await process_due_posts(bot)
        self.assertEqual(_texts(bot).count("RECENT_BODY"), 1)
        self.assertNotIn("ALREADY_SENT_BODY", _texts(bot))

        recent_row = (await self._rows(recent_at))[0]
        self.assertEqual(recent_row["status"], "sent")
        recent_sent_at = recent_row["sent_at"]
        self.assertIsNotNone(recent_sent_at)

        await _seed_posts([recent], "grace")
        await seed_week1_posts()
        await process_due_posts(bot)

        self.assertEqual(_texts(bot), ["RECENT_BODY"])
        kept_after = (await self._rows(catalog["scheduled_at"]))[0]
        self.assertEqual(kept_after["status"], "sent")
        self.assertEqual(kept_after["sent_at"], sent_at)
        recent_after = (await self._rows(recent_at))[0]
        self.assertEqual(recent_after["status"], "sent")
        self.assertEqual(recent_after["sent_at"], recent_sent_at)
        self.assertEqual(len(await self._rows(recent_at)), 1)

    async def test_stale_unsent_posts_are_not_sent_on_startup(self) -> None:
        now = datetime.now(timezone.utc)
        legacy_at = (now - timedelta(hours=5)).isoformat()
        await self._insert(scheduled_at=legacy_at, status="pending", text="LEGACY_STALE")

        await seed_week1_posts()
        await seed_week2_posts()
        first = await self._all()
        await seed_week1_posts()
        await seed_week2_posts()
        second = await self._all()

        self.assertEqual([row["id"] for row in first], [row["id"] for row in second])
        self.assertEqual(
            [row["status"] for row in first],
            [row["status"] for row in second],
        )
        scheduled = [row["scheduled_at"] for row in second]
        self.assertEqual(len(scheduled), len(set(scheduled)))

        bot = AsyncMock()
        with self.assertLogs(level="INFO") as captured:
            sent = await process_due_posts(bot)
        self.assertEqual(sent, 0)
        self.assertEqual(_texts(bot), [])
        self.assertEqual(_questions(bot), [])
        self.assertTrue(any("Skipped stale" in line for line in captured.output))

        legacy = await self._rows(legacy_at)
        self.assertEqual(len(legacy), 1)
        self.assertEqual(legacy[0]["status"], "expired")

        for post in WEEK1_POSTS + WEEK2_POSTS:
            if not _is_stale(post["scheduled_at"], now):
                continue
            rows = await self._rows(post["scheduled_at"])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "expired")
            if post.get("text_content"):
                self.assertNotIn(post["text_content"], _texts(bot))
            if post.get("poll_question"):
                self.assertNotIn(post["poll_question"], _questions(bot))

    async def test_channel_autopost_disabled_skips_seed_and_scheduler(self) -> None:
        self.assertFalse(Settings.model_fields["channel_autopost_enabled"].default)

        bot = AsyncMock()
        with patch("bot.scheduler.settings.channel_autopost_enabled", False):
            task = await start_channel_autopost(bot)

        self.assertIsNone(task)
        self.assertEqual(await self._all(), [])
        bot.send_message.assert_not_called()
        bot.send_poll.assert_not_called()

    async def test_channel_autopost_enabled_seeds_without_sending_stale(self) -> None:
        bot = AsyncMock()
        with (
            patch("bot.scheduler.settings.channel_autopost_enabled", True),
            patch("bot.scheduler.scheduler_loop", new_callable=AsyncMock) as loop,
        ):
            task = await start_channel_autopost(bot)
        self.assertIsNotNone(task)
        await task
        loop.assert_awaited_once()

        now = datetime.now(timezone.utc)
        rows = await self._all()
        self.assertEqual(len(rows), len(WEEK1_POSTS) + len(WEEK2_POSTS))
        for row in rows:
            if _is_stale(row["scheduled_at"], now):
                self.assertEqual(row["status"], "expired")
        bot.send_message.assert_not_called()
        bot.send_poll.assert_not_called()


if __name__ == "__main__":
    unittest.main()
