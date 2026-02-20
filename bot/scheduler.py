from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from bot.storage import _connect

MOSCOW_TZ = timezone(timedelta(hours=3))
CHANNEL_ID = "@shkaf_rabotaet"


# ─── Database ──────────────────────────────────────────────


async def init_scheduled_posts_table() -> None:
    async with _connect() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheduled_at TEXT NOT NULL,
                post_type TEXT NOT NULL DEFAULT 'text',
                text_content TEXT,
                poll_question TEXT,
                poll_options_json TEXT,
                channel_id TEXT NOT NULL DEFAULT '@shkaf_rabotaet',
                status TEXT NOT NULL DEFAULT 'pending',
                sent_at TEXT,
                error_message TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_scheduled_posts_status_time
            ON scheduled_posts (status, scheduled_at)
            """
        )
        await conn.commit()


async def get_due_posts() -> list[dict]:
    now_utc = datetime.now(timezone.utc).isoformat()
    async with _connect() as conn:
        cursor = await conn.execute(
            """
            SELECT id, scheduled_at, post_type, text_content,
                   poll_question, poll_options_json, channel_id
            FROM scheduled_posts
            WHERE status = 'pending' AND scheduled_at <= ?
            ORDER BY scheduled_at ASC
            """,
            (now_utc,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def mark_post_sent(post_id: int) -> None:
    now_utc = datetime.now(timezone.utc).isoformat()
    async with _connect() as conn:
        await conn.execute(
            "UPDATE scheduled_posts SET status = 'sent', sent_at = ? WHERE id = ?",
            (now_utc, post_id),
        )
        await conn.commit()


async def mark_post_failed(post_id: int, error: str) -> None:
    async with _connect() as conn:
        await conn.execute(
            "UPDATE scheduled_posts SET status = 'failed', error_message = ? WHERE id = ?",
            (error, post_id),
        )
        await conn.commit()


# ─── Sending ───────────────────────────────────────────────


async def send_scheduled_post(bot: Bot, post: dict) -> None:
    channel = post["channel_id"]

    if post["post_type"] == "poll":
        options = json.loads(post["poll_options_json"])
        await bot.send_poll(
            chat_id=channel,
            question=post["poll_question"],
            options=options,
            is_anonymous=True,
        )
    else:
        await bot.send_message(chat_id=channel, text=post["text_content"])


# ─── Background Loop ──────────────────────────────────────


async def scheduler_loop(bot: Bot) -> None:
    logging.info("Scheduler loop started")
    try:
        while True:
            try:
                due_posts = await get_due_posts()
                for post in due_posts:
                    try:
                        await send_scheduled_post(bot, post)
                        await mark_post_sent(post["id"])
                        logging.info("Scheduled post %s sent to %s", post["id"], post["channel_id"])
                    except Exception as exc:
                        await mark_post_failed(post["id"], f"{type(exc).__name__}: {exc}")
                        logging.exception("Failed to send scheduled post %s", post["id"])
            except Exception:
                logging.exception("Scheduler loop iteration failed")

            await asyncio.sleep(60)
    except asyncio.CancelledError:
        logging.info("Scheduler loop stopped")
        raise


# ─── Seed Data ─────────────────────────────────────────────


def _msk(year: int, month: int, day: int, hour: int, minute: int = 0) -> str:
    moscow_dt = datetime(year, month, day, hour, minute, tzinfo=MOSCOW_TZ)
    return moscow_dt.astimezone(timezone.utc).isoformat()


WEEK1_POSTS = [
    {
        "scheduled_at": _msk(2026, 2, 24, 9, 0),
        "post_type": "text",
        "text_content": (
            "Правило «3 цветов»\n"
            "\n"
            "Если в образе больше 3 цветов — он начинает «шуметь».\n"
            "\n"
            "Формула для утра:\n"
            "1 нейтральный (чёрный, серый, белый, беж)\n"
            "+ 1 базовый (джинсовый, хаки, бордовый)\n"
            "+ 1 акцент (если хочется)\n"
            "\n"
            "Всё. Больше не надо.\n"
            "\n"
            "Это не правило моды. Это правило спокойствия:\n"
            "ты выходишь — и не сомневаешься.\n"
            "\n"
            "Сохрани и попробуй завтра утром."
        ),
    },
    {
        "scheduled_at": _msk(2026, 2, 25, 12, 0),
        "post_type": "text",
        "text_content": (
            "3 вещи → 1 образ\n"
            "\n"
            "Белая футболка + прямые джинсы + белые кроссовки.\n"
            "\n"
            "Скучно? Нет. Это база, которая работает в 80% ситуаций.\n"
            "\n"
            "Добавь одну деталь — и характер меняется:\n"
            "• Пиджак → офис\n"
            "• Кожаная куртка → вечер\n"
            "• Шарф с принтом → выходной\n"
            "\n"
            "Не нужен новый гардероб. Нужна одна правильная деталь.\n"
            "\n"
            "Какую деталь ты добавляешь чаще всего? Напиши в комментариях 👇"
        ),
    },
    {
        "scheduled_at": _msk(2026, 2, 26, 18, 0),
        "post_type": "text",
        "text_content": (
            "Мы строим AI-стилиста в Telegram.\n"
            "\n"
            "Идея простая: ты фоткаешь свои вещи,\n"
            "а бот собирает из них образы.\n"
            "\n"
            "Не из Pinterest. Не из каталога.\n"
            "Из твоего реального шкафа.\n"
            "\n"
            "Сейчас допиливаем подбор по поводу и сезону.\n"
            "Скоро покажу, как это выглядит внутри.\n"
            "\n"
            "Подробнее: sema2944.github.io/shkaf-rabotaet\n"
            "\n"
            "Кто хочет попробовать первым — ставьте 🔥"
        ),
    },
    {
        "scheduled_at": _msk(2026, 2, 27, 11, 0),
        "post_type": "poll",
        "poll_question": "Сколько времени ты тратишь на выбор одежды утром?",
        "poll_options_json": json.dumps(
            [
                "До 5 минут — я знаю, что надеть",
                "5–15 минут — перебираю варианты",
                "15–30 минут — это реально стресс",
                "Выбираю вечером заранее",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "scheduled_at": _msk(2026, 2, 28, 9, 0),
        "post_type": "text",
        "text_content": (
            "Почему одни образы «дорого выглядят», а другие нет?\n"
            "\n"
            "Не ткань. Не бренд.\n"
            "\n"
            "Три вещи:\n"
            "\n"
            "1. Посадка — вещь сидит по фигуре, не висит\n"
            "2. Аккуратность — нет катышек, потёртостей, мятых складок\n"
            "3. Цветовая тишина — нет конфликта цветов\n"
            "\n"
            "Масс-маркет в этих трёх правилах выглядит дороже,\n"
            "чем люкс без них.\n"
            "\n"
            "Проверь свой сегодняшний образ по этим 3 пунктам.\n"
            "Что бы ты изменила?"
        ),
    },
    {
        "scheduled_at": _msk(2026, 3, 1, 12, 0),
        "post_type": "text",
        "text_content": (
            "Пятница. Офис → бар.\n"
            "\n"
            "Утро: тёмные брюки + водолазка + лоферы\n"
            "Вечер: +яркая сумка, закатать рукава, другие серьги\n"
            "\n"
            "Тот же образ. Другая энергия.\n"
            "\n"
            "Стиль — это не «что», а «как».\n"
            "\n"
            "Какой переход офис → вечер используешь ты?"
        ),
    },
    {
        "scheduled_at": _msk(2026, 3, 2, 18, 0),
        "post_type": "text",
        "text_content": (
            "Через 2 недели открываем ранний доступ к AI-стилисту.\n"
            "\n"
            "Что он умеет:\n"
            "→ Загружаешь фото своих вещей\n"
            "→ Бот распознаёт цвет, тип, сезон\n"
            "→ Собирает образы под повод: офис, прогулка, выход\n"
            "→ Показывает комбинации из твоих реальных фото\n"
            "\n"
            "Не из каталога. Из твоего шкафа.\n"
            "\n"
            "Первые 50 пользователей — бесплатный месяц.\n"
            "\n"
            "Всё о боте: sema2944.github.io/shkaf-rabotaet\n"
            "\n"
            "Хочешь в список? Напиши «+» в комментариях."
        ),
    },
]


async def seed_week1_posts() -> int:
    async with _connect() as conn:
        changed = 0
        for post in WEEK1_POSTS:
            cursor = await conn.execute(
                "SELECT id, status FROM scheduled_posts WHERE scheduled_at = ?",
                (post["scheduled_at"],),
            )
            existing = await cursor.fetchone()

            if existing:
                if existing["status"] == "pending":
                    await conn.execute(
                        """
                        UPDATE scheduled_posts
                        SET text_content = ?, poll_question = ?, poll_options_json = ?
                        WHERE id = ?
                        """,
                        (
                            post.get("text_content"),
                            post.get("poll_question"),
                            post.get("poll_options_json"),
                            existing["id"],
                        ),
                    )
                    changed += 1
                continue

            await conn.execute(
                """
                INSERT INTO scheduled_posts
                    (scheduled_at, post_type, text_content,
                     poll_question, poll_options_json, channel_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    post["scheduled_at"],
                    post["post_type"],
                    post.get("text_content"),
                    post.get("poll_question"),
                    post.get("poll_options_json"),
                    CHANNEL_ID,
                ),
            )
            changed += 1

        await conn.commit()
    logging.info("Seeded/updated %d scheduled posts (Week 1)", changed)
    return changed
