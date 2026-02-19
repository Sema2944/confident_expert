from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_user(self, telegram_id: int, username: str | None) -> User:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user:
            return user
        user = User(telegram_id=telegram_id, username=username)
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    def has_active_subscription(self, user: User) -> bool:
        if user.subscription_status != "active":
            return False
        if not user.subscription_until:
            return False
        return user.subscription_until > datetime.now(tz=timezone.utc)

    async def mark_trial_used(self, user: User) -> None:
        user.trial_used = True
        await self._session.commit()
