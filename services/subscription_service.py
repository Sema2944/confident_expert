"""Trial gating и управление подписками (SQLite)."""

from datetime import datetime

from bot.storage import _connect

FREE_OUTFIT_LIMIT = 3


async def get_or_create_user(user_id: int, username: str | None = None) -> dict:
    async with _connect() as connection:
        cursor = await connection.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,),
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)

        await connection.execute(
            """
            INSERT INTO user_profiles (user_id, username)
            VALUES (?, ?)
            """,
            (user_id, username),
        )
        await connection.commit()
        return {
            "user_id": user_id,
            "username": username,
            "trial_used": 0,
            "subscription_status": "inactive",
            "subscription_until": None,
            "outfit_requests_count": 0,
        }


async def can_generate_outfit(user_id: int) -> tuple[bool, str]:
    """Возвращает (разрешено, причина).

    Логика:
    - Первые 3 образа бесплатно (trial).
    - После trial — сообщение о подписке.
    - Активная подписка — без ограничений.
    """
    user = await get_or_create_user(user_id)

    # Активная подписка
    if user["subscription_status"] == "active":
        until = user.get("subscription_until")
        if until:
            try:
                until_dt = datetime.fromisoformat(until)
                if until_dt > datetime.now():
                    return True, ""
            except (ValueError, TypeError):
                pass

    # Trial
    count = user["outfit_requests_count"]
    if count < FREE_OUTFIT_LIMIT:
        remaining = FREE_OUTFIT_LIMIT - count
        return True, f"Пробный режим: осталось {remaining} бесплатных образов."

    from config.settings import settings as _s
    return False, (
        f"Ты попробовал {FREE_OUTFIT_LIMIT} бесплатных образа — "
        "надеюсь, тебе понравилось!\n\n"
        "С подпиской ты получишь:\n"
        "✨ Безлимитные образы на каждый день\n"
        "👗 Визуализация на манекене\n"
        "🔍 Поиск похожих вещей в магазинах\n"
        "🌤 Подбор по реальной погоде\n"
        "📊 Полная статистика гардероба\n\n"
        f"Всего {_s.subscription_price} ₽/мес — дешевле одного кофе.\n\n"
        "Нажми 💎 Подписка в меню."
    )


async def increment_outfit_count(user_id: int) -> None:
    async with _connect() as connection:
        await connection.execute(
            """
            UPDATE user_profiles
            SET outfit_requests_count = outfit_requests_count + 1
            WHERE user_id = ?
            """,
            (user_id,),
        )
        await connection.commit()


async def activate_subscription(user_id: int, days: int) -> None:
    from datetime import timedelta
    until = datetime.now() + timedelta(days=days)
    async with _connect() as connection:
        await connection.execute(
            """
            UPDATE user_profiles
            SET subscription_status = 'active', subscription_until = ?
            WHERE user_id = ?
            """,
            (until.isoformat(), user_id),
        )
        await connection.commit()
