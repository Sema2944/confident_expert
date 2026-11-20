import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bot import storage
from bot.storage import init_storage
from bot.scheduler import (
    WEEK1_POSTS,
    WEEK2_POSTS,
    _is_stale,
    _seed_posts,
    _send_daily_stats_report,
    _send_morning_outfits,
    _send_paywall_followups,
    init_scheduled_posts_table,
    process_due_posts,
    run_user_scheduler_hour,
    seed_week1_posts,
    seed_week2_posts,
    start_schedulers,
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
        await init_storage()
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

    def test_posts_mention_wardrobe_bot(self) -> None:
        blob = "\n".join(
            (post.get("text_content") or "") + (post.get("poll_question") or "")
            for post in WEEK1_POSTS + WEEK2_POSTS
        )
        self.assertNotIn("@shkaf_rabotaet_bot", blob)
        self.assertIn("@wardrobe_24_bot", blob)

    def test_scheduler_flag_defaults(self) -> None:
        self.assertFalse(Settings.model_fields["channel_autopost_enabled"].default)
        self.assertTrue(Settings.model_fields["user_scheduler_enabled"].default)

    async def test_channel_autopost_disabled_does_not_seed(self) -> None:
        bot = AsyncMock()
        with (
            patch("bot.scheduler.settings.channel_autopost_enabled", False),
            patch("bot.scheduler.settings.user_scheduler_enabled", True),
            patch("bot.scheduler.channel_post_loop", new_callable=AsyncMock) as channel_loop,
            patch("bot.scheduler.user_scheduler_loop", new_callable=AsyncMock) as user_loop,
        ):
            tasks = await start_schedulers(bot)
        self.assertEqual(len(tasks), 1)
        await tasks[0]
        channel_loop.assert_not_called()
        user_loop.assert_awaited_once()
        self.assertEqual(await self._all(), [])
        bot.send_message.assert_not_called()
        bot.send_poll.assert_not_called()

    async def test_user_scheduler_disabled_leaves_channel_flag_independent(self) -> None:
        bot = AsyncMock()
        with (
            patch("bot.scheduler.settings.channel_autopost_enabled", False),
            patch("bot.scheduler.settings.user_scheduler_enabled", False),
            patch("bot.scheduler.channel_post_loop", new_callable=AsyncMock) as channel_loop,
            patch("bot.scheduler.user_scheduler_loop", new_callable=AsyncMock) as user_loop,
        ):
            tasks = await start_schedulers(bot)
        self.assertEqual(tasks, [])
        channel_loop.assert_not_called()
        user_loop.assert_not_called()
        self.assertEqual(await self._all(), [])

    async def test_channel_autopost_enabled_seeds_without_sending_stale(self) -> None:
        bot = AsyncMock()
        with (
            patch("bot.scheduler.settings.channel_autopost_enabled", True),
            patch("bot.scheduler.settings.user_scheduler_enabled", False),
            patch("bot.scheduler.channel_post_loop", new_callable=AsyncMock) as channel_loop,
            patch("bot.scheduler.user_scheduler_loop", new_callable=AsyncMock) as user_loop,
        ):
            tasks = await start_schedulers(bot)
        self.assertEqual(len(tasks), 1)
        await tasks[0]
        channel_loop.assert_awaited_once()
        user_loop.assert_not_called()

        now = datetime.now(timezone.utc)
        rows = await self._all()
        self.assertEqual(len(rows), len(WEEK1_POSTS) + len(WEEK2_POSTS))
        for row in rows:
            if _is_stale(row["scheduled_at"], now):
                self.assertEqual(row["status"], "expired")
        bot.send_message.assert_not_called()
        bot.send_poll.assert_not_called()

    async def test_user_jobs_are_not_sent_twice_after_restart(self) -> None:
        outfit = unittest.mock.MagicMock()
        outfit.items = []
        bot = AsyncMock()
        with (
            patch("bot.storage.get_morning_push_users", AsyncMock(return_value=[{"user_id": 42}])),
            patch("bot.storage.get_items", AsyncMock(return_value=[{"id": 1}, {"id": 2}, {"id": 3}])),
            patch(
                "services.weather_service.detect_season_for_user",
                AsyncMock(return_value=("summer", "тепло")),
            ),
            patch("services.outfit_generation_service.OutfitService") as outfit_cls,
            patch("services.outfit_service.OutfitImageService") as image_cls,
        ):
            outfit_cls.return_value.generate_outfits = AsyncMock(return_value=[outfit])
            image_cls.return_value.render_outfit_image = AsyncMock(return_value=None)
            await _send_morning_outfits(bot, current_hour=8)
            await _send_morning_outfits(bot, current_hour=8)
        self.assertEqual(bot.send_message.await_count, 1)

        paywall_bot = AsyncMock()
        hit = "2026-11-16T08:00:00+00:00"
        with (
            patch(
                "bot.storage.get_paywall_followup_users",
                AsyncMock(return_value=[{"user_id": 7, "paywall_hit_at": hit}]),
            ),
            patch("bot.storage.clear_paywall_hit", AsyncMock()) as clear_hit,
        ):
            await _send_paywall_followups(paywall_bot)
            await _send_paywall_followups(paywall_bot)
        self.assertEqual(paywall_bot.send_message.await_count, 1)
        clear_hit.assert_awaited_once_with(7)

        stats_bot = AsyncMock()
        stats = {
            "new_users": 0,
            "total_users": 0,
            "items_uploaded": 0,
            "outfit_requests": 0,
            "new_subscriptions": 0,
            "errors_count": 0,
        }
        with (
            patch("bot.scheduler.settings.admin_id", 99),
            patch("bot.storage.get_stats_for_daily_report", AsyncMock(return_value=stats)),
        ):
            await _send_daily_stats_report(stats_bot)
            await _send_daily_stats_report(stats_bot)
        self.assertEqual(stats_bot.send_message.await_count, 1)
        self.assertEqual(stats_bot.send_message.await_args.args[0], 99)

    async def test_user_scheduler_hour_respects_flag_and_stats_hour(self) -> None:
        bot = AsyncMock()
        with (
            patch("bot.scheduler.settings.user_scheduler_enabled", False),
            patch("bot.scheduler._send_morning_outfits", AsyncMock()) as morning,
            patch("bot.scheduler._send_paywall_followups", AsyncMock()) as paywall,
            patch("bot.scheduler._send_daily_stats_report", AsyncMock()) as report,
        ):
            await run_user_scheduler_hour(bot, current_hour=21)
        morning.assert_not_awaited()
        paywall.assert_not_awaited()
        report.assert_not_awaited()

        with (
            patch("bot.scheduler.settings.user_scheduler_enabled", True),
            patch("bot.scheduler._send_morning_outfits", AsyncMock()) as morning,
            patch("bot.scheduler._send_paywall_followups", AsyncMock()) as paywall,
            patch("bot.scheduler._send_daily_stats_report", AsyncMock()) as report,
        ):
            await run_user_scheduler_hour(bot, current_hour=8)
            report.assert_not_awaited()
            morning.assert_awaited_once()
            paywall.assert_awaited_once()
            await run_user_scheduler_hour(bot, current_hour=21)
            report.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
