"""Проверка MAX API локально: токен, get_me, подписки webhook, delete_webhook.

Запуск из корня репозитория (нужен MAX_BOT_TOKEN в .env):

    python scripts/max_smoke.py

Cursor/CI не имеют доступа к вашему Render и реальному токену — этот скрипт
запускаете вы у себя или в Render Shell с теми же переменными, что у сервиса.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


async def _run() -> int:
    from maxapi import Bot

    token = (os.environ.get("MAX_BOT_TOKEN") or "").strip()
    if not token:
        print("ERROR: задайте MAX_BOT_TOKEN в окружении или в .env", file=sys.stderr)
        return 2

    bot = Bot(token)
    try:
        me = await bot.get_me()
        print(
            "get_me OK:",
            "user_id=", getattr(me, "user_id", None),
            "username=", getattr(me, "username", None),
            "first_name=", getattr(me, "first_name", None),
        )
        subs = await bot.get_subscriptions()
        urls = [s.url for s in (subs.subscriptions or [])]
        print("subscriptions (webhook) before delete:", len(urls))
        for u in urls:
            print(" ", u)
        await bot.delete_webhook()
        subs2 = await bot.get_subscriptions()
        urls2 = [s.url for s in (subs2.subscriptions or [])]
        print("subscriptions after delete_webhook:", len(urls2))
        return 0 if len(urls2) == 0 else 1
    except Exception as e:
        print("ERROR:", type(e).__name__, e, file=sys.stderr)
        return 1
    finally:
        await bot.close_session()


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
