import inspect
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bot import storage
from bot.routers.wardrobe import photo_without_category, set_category
from bot.states import BotStates
from bot.storage import (
    count_intro_members,
    get_club_state,
    get_payment_record,
    init_storage,
    save_payment_intent,
)
from services.payment_service import (
    amounts_match,
    create_payment,
    handle_yookassa_notification,
    yookassa_ip_allowed,
)
from services.pricing import monthly_quote, trial_quote
from services.subscription_service import (
    apply_payment_once,
    can_generate_outfit,
    get_or_create_user,
    subscription_is_active,
)


class _State:
    def __init__(self) -> None:
        self.data: dict = {}
        self.state = None

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def set_state(self, state) -> None:
        self.state = state

    async def get_data(self) -> dict:
        return dict(self.data)


class PricingTests(unittest.TestCase):
    def test_trial_is_one_ruble_for_three_days(self) -> None:
        quote = trial_quote(trial_price=1, trial_days=3)
        self.assertEqual(quote.kind, "trial")
        self.assertEqual(quote.amount_rub, 1)
        self.assertEqual(quote.days, 3)

    def test_first_50_boundary_and_three_intro_months(self) -> None:
        common = dict(club_price=990, intro_price=690, intro_months=3, intro_member_limit=50, period_days=30)
        self.assertEqual(
            monthly_quote(has_intro_slot=False, intro_months_used=0, confirmed_intro_members=0, **common).amount_rub,
            690,
        )
        self.assertEqual(
            monthly_quote(has_intro_slot=False, intro_months_used=0, confirmed_intro_members=49, **common).kind,
            "intro",
        )
        fiftieth = monthly_quote(
            has_intro_slot=False, intro_months_used=0, confirmed_intro_members=50, **common,
        )
        self.assertEqual(fiftieth.kind, "regular")
        self.assertEqual(fiftieth.amount_rub, 990)

        for used in (0, 1, 2):
            quote = monthly_quote(
                has_intro_slot=True, intro_months_used=used, confirmed_intro_members=50, **common,
            )
            self.assertEqual(quote.amount_rub, 690, used)
        after = monthly_quote(
            has_intro_slot=True, intro_months_used=3, confirmed_intro_members=10, **common,
        )
        self.assertEqual(after.kind, "regular")
        self.assertEqual(after.amount_rub, 990)

    def test_create_payment_is_sync(self) -> None:
        self.assertFalse(inspect.iscoroutinefunction(create_payment))
        import bot_max.handlers.payment as max_payment
        source = inspect.getsource(max_payment.cb_subscribe)
        self.assertNotIn("await create_payment", source)
        self.assertIn("start_checkout", source)

    def test_yookassa_ip_allowlist(self) -> None:
        self.assertTrue(yookassa_ip_allowed("185.71.76.10"))
        self.assertTrue(yookassa_ip_allowed("77.75.156.11"))
        self.assertFalse(yookassa_ip_allowed("8.8.8.8"))
        self.assertFalse(yookassa_ip_allowed("not-an-ip"))
        self.assertTrue(amounts_match("690.00", 690))
        self.assertFalse(amounts_match("1.00", 690))


class PaymentFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._prev = storage._STORAGE_PATH
        storage._STORAGE_PATH = Path(self._tmpdir.name) / "wardrobe.sqlite3"
        self.assertFalse(storage._USE_PG)
        await init_storage()

    async def asyncTearDown(self) -> None:
        storage._STORAGE_PATH = self._prev
        self._tmpdir.cleanup()

    async def test_new_user_has_no_free_outfits(self) -> None:
        allowed, text = await can_generate_outfit(501)
        self.assertFalse(allowed)
        self.assertIn("1 ₽", text)
        self.assertIn("690", text)
        self.assertIn("Автосписания нет", text)

    async def test_payment_is_idempotent_and_assigns_intro_slot(self) -> None:
        await get_or_create_user(77)
        await save_payment_intent(
            payment_id="pay_intro_1",
            user_id=77,
            amount_rub=690,
            kind="intro",
            days=30,
        )
        first = await apply_payment_once("pay_intro_1")
        self.assertIsNotNone(first)
        user = await get_or_create_user(77)
        self.assertTrue(subscription_is_active(user))
        until_after_first = str(user["subscription_until"])
        state = await get_club_state(77)
        self.assertEqual(state["intro_slot"], 1)
        self.assertEqual(state["intro_months_used"], 1)
        self.assertEqual(state["club_paid"], 1)

        second = await apply_payment_once("pay_intro_1")
        self.assertIsNone(second)
        user_again = await get_or_create_user(77)
        self.assertEqual(str(user_again["subscription_until"]), until_after_first)
        self.assertEqual((await get_club_state(77))["intro_months_used"], 1)

        await save_payment_intent(
            payment_id="pay_intro_2", user_id=77, amount_rub=690, kind="intro", days=30,
        )
        await save_payment_intent(
            payment_id="pay_intro_3", user_id=77, amount_rub=690, kind="intro", days=30,
        )
        await apply_payment_once("pay_intro_2")
        await apply_payment_once("pay_intro_3")
        self.assertEqual((await get_club_state(77))["intro_months_used"], 3)
        quote = monthly_quote(
            has_intro_slot=True,
            intro_months_used=3,
            confirmed_intro_members=await count_intro_members(),
            club_price=990,
            intro_price=690,
            intro_months=3,
            intro_member_limit=50,
            period_days=30,
        )
        self.assertEqual(quote.amount_rub, 990)

    async def test_fiftieth_member_closes_intro_price(self) -> None:
        for index in range(50):
            user_id = 1000 + index
            await get_or_create_user(user_id)
            await save_payment_intent(
                payment_id=f"slot_{index}",
                user_id=user_id,
                amount_rub=690,
                kind="intro",
                days=30,
            )
            claimed = await apply_payment_once(f"slot_{index}")
            self.assertEqual(claimed["kind"], "intro")
        self.assertEqual(await count_intro_members(), 50)
        from services.subscription_service import quote_monthly_for_user
        await get_or_create_user(4242)
        quote = await quote_monthly_for_user(4242)
        self.assertEqual(quote.kind, "regular")
        self.assertEqual(quote.amount_rub, 990)

    async def test_webhook_verifies_amount_and_does_not_activate_twice(self) -> None:
        await get_or_create_user(88)
        await save_payment_intent(
            payment_id="pay_ok",
            user_id=88,
            amount_rub=1,
            kind="trial",
            days=3,
        )
        body = {"event": "payment.succeeded", "object": {"id": "pay_ok", "metadata": {"user_id": "1"}}}

        def fetch_ok(_payment_id: str) -> dict:
            return {
                "id": "pay_ok",
                "status": "succeeded",
                "amount": "1.00",
                "currency": "RUB",
                "user_id": "88",
            }

        with patch("services.payment_service.settings.yookassa_ip_check", True):
            rejected = await handle_yookassa_notification(
                body=body,
                source_ip="8.8.8.8",
                fetch_payment=fetch_ok,
            )
        self.assertEqual(rejected["status"], 403)
        self.assertFalse(rejected["activated"])
        self.assertEqual((await get_payment_record("pay_ok"))["status"], "pending")

        mismatch = await handle_yookassa_notification(
            body=body,
            source_ip="185.71.76.5",
            fetch_payment=lambda _pid: {**fetch_ok(_pid), "amount": "990.00"},
        )
        self.assertEqual(mismatch["reason"], "amount")
        self.assertFalse(subscription_is_active(await get_or_create_user(88)))

        with patch("services.payment_service.settings.yookassa_ip_check", True):
            ok = await handle_yookassa_notification(
                body=body,
                source_ip="185.71.76.5",
                fetch_payment=fetch_ok,
            )
        self.assertTrue(ok["activated"])
        self.assertEqual(ok["days"], 3)
        user = await get_or_create_user(88)
        self.assertTrue(subscription_is_active(user))
        until = user["subscription_until"]
        parsed = datetime.fromisoformat(str(until))
        self.assertLess(abs((parsed.replace(tzinfo=None) - datetime.now()).days - 3), 2)

        again = await handle_yookassa_notification(
            body=body,
            source_ip="185.71.76.5",
            fetch_payment=fetch_ok,
        )
        self.assertFalse(again["activated"])
        self.assertEqual(again["reason"], "duplicate")
        user_again = await get_or_create_user(88)
        self.assertEqual(str(user_again["subscription_until"]), str(until))
        self.assertEqual((await get_club_state(88))["trial_paid"], 1)
        self.assertIsNone((await get_club_state(88))["intro_slot"])

    async def test_photo_from_menu_asks_category_then_continues(self) -> None:
        state = _State()
        message = AsyncMock()
        message.photo = [type("Photo", (), {"file_id": "file-1"})()]
        message.text = None
        await photo_without_category(message, state)
        self.assertEqual(state.state, BotStates.upload_category)
        self.assertEqual(state.data["pending_photo_file_id"], "file-1")
        answer = message.answer.await_args.args[0]
        self.assertIn("категор", answer.lower())

        message.text = "👕 Верх"
        with patch("bot.routers.wardrobe._process_wardrobe_photo", new_callable=AsyncMock) as process:
            await set_category(message, state)
        process.assert_awaited_once()
        self.assertEqual(process.await_args.args[2], "file-1")
        self.assertIsNone(state.data["pending_photo_file_id"])
        self.assertEqual(state.data["category"], "top")


class StorageLogTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_logs_sqlite_backend(self) -> None:
        with self.assertLogs("bot.storage", level="INFO") as captured:
            await init_storage()
        self.assertTrue(any("Storage backend: SQLite" in line for line in captured.output))


if __name__ == "__main__":
    unittest.main()
