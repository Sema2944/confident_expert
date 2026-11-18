import logging
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from bot.main import log_telegram_identity
from bot.middlewares.update_log import IncomingUpdateLogMiddleware, describe_incoming_update


def _user(user_id: int, first_name: str = "Секретное Имя") -> SimpleNamespace:
    return SimpleNamespace(id=user_id, first_name=first_name, username="secret_user")


class UpdateLogTests(unittest.IsolatedAsyncioTestCase):
    def test_describe_command_callback_and_photo_without_personal_text(self) -> None:
        command = SimpleNamespace(
            message=SimpleNamespace(
                text="/start@wardrobe_24_bot мой телефон +79990001122",
                caption=None,
                photo=None,
                voice=None,
                audio=None,
                video=None,
                video_note=None,
                document=None,
                sticker=None,
                location=None,
                contact=None,
                from_user=_user(42),
            )
        )
        self.assertEqual(describe_incoming_update(command), ("command", 42, "/start"))

        photo = SimpleNamespace(
            message=SimpleNamespace(
                text=None,
                caption="подпись с адресом и телефоном",
                photo=[SimpleNamespace(file_id="file")],
                voice=None,
                audio=None,
                video=None,
                video_note=None,
                document=None,
                sticker=None,
                location=None,
                contact=None,
                from_user=_user(7),
            )
        )
        self.assertEqual(describe_incoming_update(photo), ("photo", 7, None))

        plain = SimpleNamespace(
            message=SimpleNamespace(
                text="меня зовут Анна, вот мой адрес",
                caption=None,
                photo=None,
                voice=None,
                audio=None,
                video=None,
                video_note=None,
                document=None,
                sticker=None,
                location=None,
                contact=None,
                from_user=_user(9),
            )
        )
        self.assertEqual(describe_incoming_update(plain), ("message", 9, None))

        callback = SimpleNamespace(
            message=None,
            edited_message=None,
            callback_query=SimpleNamespace(data="pay:subscribe", from_user=_user(11)),
        )
        self.assertEqual(
            describe_incoming_update(callback),
            ("callback_query", 11, "pay:subscribe"),
        )

    async def test_middleware_log_omits_message_text_and_photo_caption(self) -> None:
        event = SimpleNamespace(
            message=SimpleNamespace(
                text=None,
                caption="секретная подпись фото",
                photo=[SimpleNamespace(file_id="abc")],
                voice=None,
                audio=None,
                video=None,
                video_note=None,
                document=None,
                sticker=None,
                location=None,
                contact=None,
                from_user=_user(15, first_name="Мария"),
            ),
            edited_message=None,
            callback_query=None,
        )
        middleware = IncomingUpdateLogMiddleware()

        async def handler(update, data):
            return "handled"

        with self.assertLogs("bot.middlewares.update_log", level=logging.INFO) as captured:
            result = await middleware(handler, event, {})

        self.assertEqual(result, "handled")
        blob = "\n".join(captured.output)
        self.assertIn("type=photo", blob)
        self.assertIn("user_id=15", blob)
        self.assertNotIn("секретная подпись", blob)
        self.assertNotIn("Мария", blob)
        self.assertNotIn("secret_user", blob)

    async def test_log_telegram_identity_writes_username(self) -> None:
        bot = AsyncMock()
        me = MagicMock()
        me.id = 100
        me.username = "wardrobe_24_bot"
        bot.get_me.return_value = me

        with self.assertLogs(level=logging.INFO) as captured:
            await log_telegram_identity(bot)

        blob = "\n".join(captured.output)
        self.assertIn("Telegram getMe: id=100 username=@wardrobe_24_bot", blob)

    async def test_log_telegram_identity_swallows_get_me_error(self) -> None:
        bot = AsyncMock()
        bot.get_me.side_effect = RuntimeError("network")
        await log_telegram_identity(bot)
