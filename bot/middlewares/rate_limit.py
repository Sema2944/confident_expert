import time
from collections import defaultdict, deque

from aiogram import BaseMiddleware
from aiogram.types import Message

from config.settings import settings


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._uploads: dict[int, deque[float]] = defaultdict(deque)
        self._limit = settings.rate_limit_upload_per_min
        super().__init__()

    async def __call__(self, handler, event: Message, data):
        if not isinstance(event, Message) or not event.photo:
            return await handler(event, data)

        now = time.time()
        queue = self._uploads[event.from_user.id]
        while queue and now - queue[0] > 60:
            queue.popleft()

        if len(queue) >= self._limit:
            await event.answer("Слишком много фото. Попробуйте чуть позже.")
            return None

        queue.append(now)
        return await handler(event, data)
