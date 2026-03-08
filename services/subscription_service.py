"""Trial gating и управление подписками."""

from datetime import datetime

from bot.storage import _connect, _ph, _USE_PG


FREE_OUTFIT_LIMIT = 3


async def get_or_create_user(user_id: int, username: str | None = None) -> dict:
    async with _connect() as db:
        row = await db.fetchone(
            f"SELECT * FROM user_profiles WHERE user_id = {_ph(1)}", (user_id,),
        )
        if row:
            return dict(row)

        if _USE_PG:
            await db.execute(
                "INSERT INTO user_profiles (user_id, username) VALUES ($1, $2) "
                "ON CONFLICT (user_id) DO NOTHING",
                (user_id, username),
            )
        else:
            await db.execute(
                "INSERT INTO user_profiles (user_id, username) VALUES (?, ?)",
                (user_id, username),
            )
            await db.commit()

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
                until_dt = datetime.fromisoformat(str(until)) if not isinstance(until, datetime) else until
                if until_dt.replace(tzinfo=None) > datetime.now():
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
    async with _connect() as db:
        await db.execute(
            f"UPDATE user_profiles SET outfit_requests_count = outfit_requests_count + 1 "
            f"WHERE user_id = {_ph(1)}",
            (user_id,),
        )
        await db.commit()


async def activate_subscription(user_id: int, days: int) -> None:
    from datetime import timedelta, timezone as _tz
    from bot.storage import _now_ts
    now = datetime.now(_tz.utc) if _USE_PG else datetime.now()
    until = now + timedelta(days=days)
    if not _USE_PG:
        until = until.isoformat()
    async with _connect() as db:
        await db.execute(
            f"UPDATE user_profiles SET subscription_status = 'active', subscription_until = {_ph(1)} "
            f"WHERE user_id = {_ph(2)}",
            (until, user_id),
        )
        await db.commit()
