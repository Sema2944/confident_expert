"""Доступ в клуб и срок подписки."""

from datetime import datetime, timedelta, timezone

from bot.storage import (
    _USE_PG,
    _connect,
    _ph,
    _transaction,
    count_intro_members,
    get_club_state,
    get_payment_record,
)
from services.pricing import PriceQuote, active_subscription_text, monthly_quote, paywall_text


def subscription_is_active(user: dict, now: datetime | None = None) -> bool:
    if user.get("subscription_status") != "active":
        return False
    until = user.get("subscription_until")
    if not until:
        return False
    current = now or datetime.now()
    try:
        until_dt = until if isinstance(until, datetime) else datetime.fromisoformat(str(until))
    except (ValueError, TypeError):
        return False
    return until_dt.replace(tzinfo=None) > current.replace(tzinfo=None)


def format_until(until: object) -> str:
    if isinstance(until, datetime):
        return until.strftime("%d.%m.%Y")
    text = str(until or "")
    if len(text) >= 10 and text[4] == "-":
        year, month, day = text[:10].split("-")
        return f"{day}.{month}.{year}"
    return text[:10] or "—"


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


async def quote_monthly_for_user(user_id: int) -> PriceQuote:
    state = await get_club_state(user_id)
    members = await count_intro_members()
    return monthly_quote(
        has_intro_slot=state.get("intro_slot") is not None,
        intro_months_used=int(state.get("intro_months_used") or 0),
        confirmed_intro_members=members,
    )


async def describe_offer(user_id: int) -> dict:
    """Текст и цена следующего периода для экранов оплаты."""
    user = await get_or_create_user(user_id)
    state = await get_club_state(user_id)
    quote = await quote_monthly_for_user(user_id)
    active = subscription_is_active(user)
    trial_available = not active and not int(state.get("trial_paid") or 0) and not int(state.get("club_paid") or 0)
    until_label = format_until(user.get("subscription_until"))
    if active:
        screen = active_subscription_text(until_label, quote)
    else:
        screen = paywall_text(quote=quote, trial_available=trial_available)
    return {
        "user": user,
        "quote": quote,
        "active": active,
        "trial_available": trial_available,
        "until_label": until_label,
        "paywall_text": paywall_text(quote=quote, trial_available=trial_available),
        "screen_text": screen,
    }


async def can_generate_outfit(user_id: int) -> tuple[bool, str]:
    """Активный клуб разрешает образы. Бесплатных образов нет."""
    user = await get_or_create_user(user_id)
    if subscription_is_active(user):
        return True, ""
    offer = await describe_offer(user_id)
    return False, offer["paywall_text"]


async def increment_outfit_count(user_id: int) -> None:
    async with _connect() as db:
        await db.execute(
            f"UPDATE user_profiles SET outfit_requests_count = outfit_requests_count + 1 "
            f"WHERE user_id = {_ph(1)}",
            (user_id,),
        )
        await db.commit()


def _as_naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


async def extend_subscription(user_id: int, days: int, *, db=None) -> None:
    """Продлевает клуб на days от max(сейчас, текущий срок)."""
    now = datetime.now(timezone.utc) if _USE_PG else datetime.now()

    async def _apply(connection) -> None:
        row = await connection.fetchone(
            f"SELECT subscription_until FROM user_profiles WHERE user_id = {_ph(1)}",
            (user_id,),
        )
        base = now
        raw_until = row.get("subscription_until") if row else None
        if raw_until:
            try:
                until_dt = raw_until if isinstance(raw_until, datetime) else datetime.fromisoformat(str(raw_until))
                if _as_naive(until_dt) > _as_naive(now):
                    base = until_dt
            except (ValueError, TypeError):
                pass
        new_until = base + timedelta(days=days)
        if not _USE_PG:
            new_until = _as_naive(new_until).isoformat()
        await connection.execute(
            f"UPDATE user_profiles SET subscription_status = 'active', subscription_until = {_ph(1)} "
            f"WHERE user_id = {_ph(2)}",
            (new_until, user_id),
        )

    if db is not None:
        await _apply(db)
        return
    await get_or_create_user(user_id)
    async with _connect() as connection:
        await _apply(connection)
        await connection.commit()


async def activate_subscription(user_id: int, days: int) -> None:
    await extend_subscription(user_id, days)


async def _write_club_payment(db, claimed: dict) -> None:
    user_id = int(claimed["user_id"])
    kind = claimed["kind"]
    row = await db.fetchone(
        f"""
        SELECT trial_paid, club_paid, intro_slot, intro_months_used
        FROM club_members WHERE user_id = {_ph(1)}
        """,
        (user_id,),
    )
    trial_paid = int(row.get("trial_paid") or 0) if row else 0
    club_paid = int(row.get("club_paid") or 0) if row else 0
    slot = row.get("intro_slot") if row else None
    used = int(row.get("intro_months_used") or 0) if row else 0
    if kind == "trial":
        trial_paid = 1
    else:
        club_paid = 1
        if kind == "intro":
            if slot is None:
                count = await db.fetchval(
                    "SELECT COUNT(*) FROM club_members WHERE intro_slot IS NOT NULL"
                )
                slot = int(count or 0) + 1
            used += 1
    if row:
        await db.execute(
            f"""
            UPDATE club_members
            SET trial_paid = {_ph(1)}, club_paid = {_ph(2)},
                intro_slot = {_ph(3)}, intro_months_used = {_ph(4)}
            WHERE user_id = {_ph(5)}
            """,
            (trial_paid, club_paid, slot, used, user_id),
        )
        return
    await db.execute(
        f"""
        INSERT INTO club_members
            (user_id, trial_paid, club_paid, intro_slot, intro_months_used)
        VALUES ({_ph(1)}, {_ph(2)}, {_ph(3)}, {_ph(4)}, {_ph(5)})
        """,
        (user_id, trial_paid, club_paid, slot, used),
    )


async def apply_payment_once(payment_id: str) -> dict | None:
    """Активирует платёж один раз. Повторный payment_id ничего не продлевает."""
    record = await get_payment_record(payment_id)
    if record:
        await get_or_create_user(int(record["user_id"]))
    async with _transaction() as db:
        claimed = await db.fetchone(
            f"""
            UPDATE payment_records SET status = 'succeeded'
            WHERE payment_id = {_ph(1)} AND status = 'pending'
            RETURNING payment_id, user_id, amount_rub, kind, days
            """,
            (payment_id,),
        )
        if not claimed:
            return None
        await extend_subscription(int(claimed["user_id"]), int(claimed["days"]), db=db)
        await _write_club_payment(db, claimed)
        await db.commit()
        return claimed
