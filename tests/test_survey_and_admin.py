import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.admin_notify_service import AdminNotifyService


class AdminNotifyServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_notify_sends_message_when_admin_id_set(self) -> None:
        bot = AsyncMock()
        with patch("services.admin_notify_service.settings") as mock_settings:
            mock_settings.admin_id = 12345
            await AdminNotifyService.notify(bot, "Test message")
        bot.send_message.assert_called_once_with(12345, "Test message", parse_mode="HTML")

    async def test_notify_skips_when_admin_id_zero(self) -> None:
        bot = AsyncMock()
        with patch("services.admin_notify_service.settings") as mock_settings:
            mock_settings.admin_id = 0
            await AdminNotifyService.notify(bot, "Test message")
        bot.send_message.assert_not_called()

    async def test_notify_swallows_bot_error(self) -> None:
        bot = AsyncMock()
        bot.send_message.side_effect = Exception("Connection failed")
        with patch("services.admin_notify_service.settings") as mock_settings:
            mock_settings.admin_id = 12345
            # Should not raise
            await AdminNotifyService.notify(bot, "Test message")


class SurveyRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_show_survey_if_eligible_sends_message_when_eligible(self) -> None:
        bot = AsyncMock()
        with (
            patch("bot.routers.survey.should_show_survey", return_value=True),
            patch("bot.routers.survey.update_survey_shown_at"),
        ):
            from bot.routers.survey import show_survey_if_eligible
            await show_survey_if_eligible(bot, user_id=999)
        bot.send_message.assert_called_once()
        args = bot.send_message.call_args
        assert args[0][0] == 999  # user_id is first positional arg

    async def test_show_survey_if_eligible_skips_when_not_eligible(self) -> None:
        bot = AsyncMock()
        with patch("bot.routers.survey.should_show_survey", return_value=False):
            from bot.routers.survey import show_survey_if_eligible
            await show_survey_if_eligible(bot, user_id=999)
        bot.send_message.assert_not_called()

    async def test_show_survey_if_eligible_swallows_error(self) -> None:
        bot = AsyncMock()
        bot.send_message.side_effect = Exception("Network error")
        with (
            patch("bot.routers.survey.should_show_survey", return_value=True),
            patch("bot.routers.survey.update_survey_shown_at"),
        ):
            from bot.routers.survey import show_survey_if_eligible
            # Should not raise
            await show_survey_if_eligible(bot, user_id=999)


class SurveyKeyboardTests(unittest.TestCase):
    def test_rating_keyboard_has_5_rating_buttons(self) -> None:
        from bot.routers.survey import _survey_rating_keyboard
        kb = _survey_rating_keyboard()
        rating_row = kb.inline_keyboard[0]
        self.assertEqual(len(rating_row), 5)
        for i, btn in enumerate(rating_row, 1):
            self.assertEqual(btn.callback_data, f"survey:rate:{i}")

    def test_rating_keyboard_has_skip_button(self) -> None:
        from bot.routers.survey import _survey_rating_keyboard
        kb = _survey_rating_keyboard()
        skip_row = kb.inline_keyboard[1]
        self.assertEqual(skip_row[0].callback_data, "survey:skip")

    def test_value_keyboard_has_all_options(self) -> None:
        from bot.routers.survey import _survey_value_keyboard, _VALUE_OPTIONS
        kb = _survey_value_keyboard()
        # Last row is skip, rest are value options
        value_rows = kb.inline_keyboard[:-1]
        self.assertEqual(len(value_rows), len(_VALUE_OPTIONS))

    def test_value_keyboard_has_skip_button(self) -> None:
        from bot.routers.survey import _survey_value_keyboard
        kb = _survey_value_keyboard()
        skip_row = kb.inline_keyboard[-1]
        self.assertEqual(skip_row[0].callback_data, "survey:skip")


if __name__ == "__main__":
    unittest.main()
