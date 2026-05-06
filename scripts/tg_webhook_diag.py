"""Диагностика Telegram-бота: getMe и getWebhookInfo (BOT_TOKEN не выводится).

Запуск из корня репозитория:

    python scripts/tg_webhook_diag.py

Нужен BOT_TOKEN в окружении или в .env. Используйте для проверки, что токен на Render
соответствует нужному боту (@wardrobe_24_bot) и вебхук не в ошибке.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> None:
    token = (os.environ.get("BOT_TOKEN") or "").strip()
    if not token:
        print(
            "ERROR: задайте BOT_TOKEN (локально в .env или в переменных Render).",
            file=sys.stderr,
        )
        raise SystemExit(2)

    base = f"https://api.telegram.org/bot{token}"
    with httpx.Client(timeout=30.0) as client:
        me = client.get(f"{base}/getMe").json()
        wh = client.get(f"{base}/getWebhookInfo").json()

    print("=== getMe ===")
    print(json.dumps(me, indent=2, ensure_ascii=False))
    print("\n=== getWebhookInfo ===")
    print(json.dumps(wh, indent=2, ensure_ascii=False))

    if me.get("ok") and me.get("result"):
        u = me["result"].get("username")
        print(f"\nБот в токене: @{u}" if u else "\n(username отсутствует в ответе)")
    if wh.get("ok") and wh.get("result"):
        w = wh["result"]
        err = w.get("last_error_message")
        if err:
            print(f"\n⚠ Последняя ошибка вебхука у Telegram: {err}")
        if not (w.get("url") or "").strip():
            print("\nВебхук URL пустой — используется long polling или вебхук ещё не установлен.")

    raise SystemExit(0 if me.get("ok") and wh.get("ok") else 1)


if __name__ == "__main__":
    main()
