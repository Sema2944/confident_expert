from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Item


class WardrobeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_item(self, user_id: int, category: str, telegram_file_id: str) -> Item:
        item = Item(
            user_id=user_id,
            category=category,
            telegram_file_id=telegram_file_id,
        )
        self._session.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        return item
