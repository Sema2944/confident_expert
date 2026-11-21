import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from bot import storage
from bot.free_text import interpret_free_text
from bot.routers.outfits import _generate_and_show_multi_outfits
from bot.routers.payment import _send_checkout
from bot.storage import _connect, _ph, get_payment_record, init_storage, save_payment_intent
from services.payment_service import (
    check_latest_user_payment,
    handle_yookassa_notification,
    payment_check_text,
    reconcile_recent_pending_payments,
)
from services.subscription_service import get_or_create_user, subscription_is_active
from services.weather_service import (
    cache_key,
    clear_weather_cache,
    detect_season_for_user,
    get_current_temperature,
    maybe_refresh_active_cities,
)


def _remote(payment_id: str, status: str, user_id: int = 77, amount: str = "1.00") -> dict:
    return {
        "id": payment_id,
        "status": status,
        "amount": amount,
        "currency": "RUB",
        "user_id": str(user_id),
    }


class FreeTextTests(unittest.TestCase):
    def test_typos_and_occasions(self) -> None:
        self.assertEqual(interpret_free_text("собири образ"), "outfit")
        self.assertEqual(interpret_free_text("Собрать образ"), "outfit")
        self.assertEqual(interpret_free_text("🏢 Работа/офис"), "work_office")
        self.assertEqual(interpret_free_text("на работу"), "work_office")
        self.assertEqual(interpret_free_text("собери образ на свидание"), "date")
        self.assertIsNone(interpret_free_text("привет, как дела"))


class PaymentConfirmTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._prev = storage._STORAGE_PATH
        storage._STORAGE_PATH = Path(self._tmpdir.name) / "wardrobe.sqlite3"
        self.assertFalse(storage._USE_PG)
        await init_storage()
        await get_or_create_user(77)

    async def asyncTearDown(self) -> None:
        storage._STORAGE_PATH = self._prev
        self._tmpdir.cleanup()

    async def _set_created_at(self, payment_id: str, created_at: str) -> None:
        async with _connect() as db:
            await db.execute(
                f"UPDATE payment_records SET created_at = {_ph(1)} WHERE payment_id = {_ph(2)}",
                (created_at, payment_id),
            )
            await db.commit()

    async def test_succeeded_pending_canceled_and_repeat(self) -> None:
        await save_payment_intent(
            payment_id="pay_old", user_id=77, amount_rub=1, kind="trial", days=3,
        )
        await self._set_created_at("pay_old", "2026-11-21T17:20:00+00:00")

        pending = await check_latest_user_payment(
            77, source="button", fetch_payment=lambda _pid: _remote("pay_old", "pending"),
        )
        self.assertEqual(pending["outcome"], "pending")
        self.assertIn("обрабатывается", payment_check_text(pending["outcome"]))
        self.assertFalse(subscription_is_active(await get_or_create_user(77)))

        canceled = await check_latest_user_payment(
            77, source="button", fetch_payment=lambda _pid: _remote("pay_old", "canceled"),
        )
        self.assertEqual(canceled["outcome"], "canceled")
        self.assertEqual((await get_payment_record("pay_old"))["status"], "canceled")

        await save_payment_intent(
            payment_id="pay_ok", user_id=77, amount_rub=1, kind="trial", days=3,
        )
        activated = await check_latest_user_payment(
            77, source="button", fetch_payment=lambda _pid: _remote("pay_ok", "succeeded"),
        )
        self.assertEqual(activated["outcome"], "activated")
        user = await get_or_create_user(77)
        self.assertTrue(subscription_is_active(user))
        until = str(user["subscription_until"])

        again = await check_latest_user_payment(
            77, source="button", fetch_payment=lambda _pid: _remote("pay_ok", "succeeded"),
        )
        self.assertEqual(again["outcome"], "already_active")
        self.assertEqual(str((await get_or_create_user(77))["subscription_until"]), until)

    async def test_webhook_then_button_does_not_extend_twice(self) -> None:
        await save_payment_intent(
            payment_id="pay_hook", user_id=77, amount_rub=1, kind="trial", days=3,
        )
        body = {"event": "payment.succeeded", "object": {"id": "pay_hook"}}
        with unittest.mock.patch("services.payment_service.settings.yookassa_ip_check", True):
            first = await handle_yookassa_notification(
                body=body,
                source_ip="185.71.76.5",
                fetch_payment=lambda _pid: _remote("pay_hook", "succeeded"),
            )
        self.assertTrue(first["activated"])
        until = str((await get_or_create_user(77))["subscription_until"])
        second = await check_latest_user_payment(
            77, source="button", fetch_payment=lambda _pid: _remote("pay_hook", "succeeded"),
        )
        self.assertEqual(second["outcome"], "already_active")
        self.assertEqual(str((await get_or_create_user(77))["subscription_until"]), until)

    async def test_old_pending_extends_active_club_from_current_end(self) -> None:
        await save_payment_intent(
            payment_id="pay_trial", user_id=77, amount_rub=1, kind="trial", days=3,
        )
        await check_latest_user_payment(
            77, source="button", fetch_payment=lambda _pid: _remote("pay_trial", "succeeded"),
        )
        until_after_trial = datetime.fromisoformat(
            str((await get_or_create_user(77))["subscription_until"])
        ).replace(tzinfo=None)

        await save_payment_intent(
            payment_id="pay_month", user_id=77, amount_rub=990, kind="regular", days=30,
        )
        await self._set_created_at("pay_month", "2020-01-01T00:00:00+00:00")
        result = await check_latest_user_payment(
            77,
            source="button",
            fetch_payment=lambda _pid: _remote("pay_month", "succeeded", amount="990.00"),
        )
        self.assertEqual(result["outcome"], "activated")
        until_after_month = datetime.fromisoformat(
            str((await get_or_create_user(77))["subscription_until"])
        ).replace(tzinfo=None)
        self.assertGreater(until_after_month, until_after_trial + timedelta(days=29))
        self.assertLess(until_after_month, until_after_trial + timedelta(days=31))

        await save_payment_intent(
            payment_id="pay_trial_again", user_id=77, amount_rub=1, kind="trial", days=3,
        )
        repeated = await check_latest_user_payment(
            77, source="button", fetch_payment=lambda _pid: _remote("pay_trial_again", "succeeded"),
        )
        self.assertEqual(repeated["outcome"], "activated")
        until_after_second_trial = datetime.fromisoformat(
            str((await get_or_create_user(77))["subscription_until"])
        ).replace(tzinfo=None)
        self.assertGreater(until_after_second_trial, until_after_month + timedelta(days=2))
        self.assertLess(until_after_second_trial, until_after_month + timedelta(days=4))

        skipped = await reconcile_recent_pending_payments(
            fetch_payment=lambda _pid: _remote(_pid, "succeeded"),
        )
        self.assertEqual(skipped, [])

    async def test_scheduler_confirms_recent_pending_only(self) -> None:
        await save_payment_intent(
            payment_id="pay_recent", user_id=77, amount_rub=1, kind="trial", days=3,
        )
        await save_payment_intent(
            payment_id="pay_ancient", user_id=77, amount_rub=990, kind="regular", days=30,
        )
        await self._set_created_at("pay_ancient", "2020-01-01T00:00:00+00:00")

        def fetch(payment_id: str) -> dict:
            amount = "1.00" if payment_id == "pay_recent" else "990.00"
            return _remote(payment_id, "succeeded", amount=amount)

        results = await reconcile_recent_pending_payments(fetch_payment=fetch)
        self.assertEqual([item["payment_id"] for item in results], ["pay_recent"])
        self.assertEqual(results[0]["outcome"], "activated")
        self.assertEqual((await get_payment_record("pay_ancient"))["status"], "pending")

        caught = await check_latest_user_payment(77, source="button", fetch_payment=fetch)
        self.assertEqual(caught["payment_id"], "pay_ancient")
        self.assertEqual(caught["outcome"], "activated")

    async def test_checkout_offers_paid_button(self) -> None:
        callback = MagicMock()
        callback.from_user.id = 77
        callback.message = AsyncMock()
        with unittest.mock.patch(
            "bot.routers.payment.is_yookassa_configured", return_value=True,
        ), unittest.mock.patch(
            "bot.routers.payment.start_checkout",
            new=AsyncMock(return_value={"payment_id": "p1", "confirmation_url": "https://pay.example"}),
        ):
            await _send_checkout(callback, "trial")
        markup = callback.message.answer.await_args.kwargs["reply_markup"]
        buttons = [button for row in markup.inline_keyboard for button in row]
        self.assertTrue(any(button.callback_data == "pay:check" for button in buttons))
        self.assertTrue(any(button.url == "https://pay.example" for button in buttons))


class OutfitAndWeatherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._prev = storage._STORAGE_PATH
        storage._STORAGE_PATH = Path(self._tmpdir.name) / "wardrobe.sqlite3"
        await init_storage()
        clear_weather_cache()

    async def asyncTearDown(self) -> None:
        clear_weather_cache()
        storage._STORAGE_PATH = self._prev
        self._tmpdir.cleanup()

    async def test_nonpayer_gets_offer_without_a_fake_generating_line(self) -> None:
        message = AsyncMock()
        message.from_user.id = 88
        state = AsyncMock()
        with unittest.mock.patch(
            "bot.routers.outfits.can_generate_outfit",
            new=AsyncMock(return_value=(False, "клуб")),
        ), unittest.mock.patch(
            "bot.routers.outfits.club_paywall",
            new=AsyncMock(return_value=("Клуб «Шкаф работает»", None)),
        ), unittest.mock.patch(
            "bot.routers.outfits.record_paywall_hit",
            new=AsyncMock(),
        ), unittest.mock.patch(
            "bot.routers.outfits.outfit_service.generate_outfits_around_base",
            new=AsyncMock(),
        ) as generate:
            await _generate_and_show_multi_outfits(
                message, state, "work_office", "summer", 1, [], {"id": 1},
            )
        generate.assert_not_awaited()
        texts = [call.args[0] for call in message.answer.await_args_list]
        self.assertEqual(texts, ["Клуб «Шкаф работает»"])
        self.assertNotIn("Подбираю 3 образа…", texts)

    async def test_rate_limit_uses_last_temperature_without_traceback(self) -> None:
        import httpx

        class _Client:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, *args, **kwargs):
                request = httpx.Request("GET", "https://api.open-meteo.com/v1/forecast")
                response = httpx.Response(429, request=request)
                raise httpx.HTTPStatusError("limited", request=request, response=response)

        clear_weather_cache()
        from services import weather_service
        weather_service._weather_cache[cache_key(None, 55.7558, 37.6173)] = (
            4.0,
            datetime.now() - timedelta(minutes=40),
        )
        with unittest.mock.patch("services.weather_service.httpx.AsyncClient", _Client):
            with self.assertLogs("services.weather_service", level="WARNING") as captured:
                temp = await get_current_temperature(55.7558, 37.6173)
        self.assertEqual(temp, 4.0)
        blob = "\n".join(captured.output)
        self.assertIn("429", blob)
        self.assertNotIn("Traceback", blob)

    async def test_rate_limit_without_cache_returns_none(self) -> None:
        import httpx

        class _Client:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, *args, **kwargs):
                request = httpx.Request("GET", "https://api.open-meteo.com/v1/forecast")
                response = httpx.Response(429, request=request)
                raise httpx.HTTPStatusError("limited", request=request, response=response)

        clear_weather_cache()
        with unittest.mock.patch("services.weather_service.httpx.AsyncClient", _Client):
            temp = await get_current_temperature(1.0, 2.0)
        self.assertIsNone(temp)

    async def test_yesterday_reading_is_not_reused(self) -> None:
        import httpx
        from services import weather_service

        class _Client:
            def __init__(self, *args, **kwargs) -> None:
                self.timeout = kwargs.get("timeout")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, *args, **kwargs):
                request = httpx.Request("GET", "https://api.open-meteo.com/v1/forecast")
                response = httpx.Response(429, request=request)
                raise httpx.HTTPStatusError("limited", request=request, response=response)

        clear_weather_cache()
        weather_service._weather_cache[cache_key("Москва", 55.75, 37.62)] = (
            20.0,
            datetime.now() - timedelta(days=1),
        )
        with unittest.mock.patch("services.weather_service.httpx.AsyncClient", _Client):
            temp = await get_current_temperature(55.75, 37.62, city="Москва")
        self.assertIsNone(temp)
        self.assertLessEqual(weather_service.SOURCE_TIMEOUT * 2, 3)

    async def test_wttr_is_used_when_open_meteo_fails(self) -> None:
        class _Response:
            def __init__(self, payload: dict) -> None:
                self._payload = payload

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return self._payload

        class _Client:
            def __init__(self, *args, **kwargs) -> None:
                self.timeout = kwargs.get("timeout")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, url, *args, **kwargs):
                if "wttr.in" in str(url):
                    return _Response({"current_condition": [{"temp_C": "7"}]})
                raise RuntimeError("open-meteo down")

        clear_weather_cache()
        with unittest.mock.patch("services.weather_service.httpx.AsyncClient", _Client):
            temp = await get_current_temperature(55.75, 37.62, city="Москва")
        self.assertEqual(temp, 7.0)

    async def test_fresh_cache_skips_network(self) -> None:
        from services import weather_service

        clear_weather_cache()
        weather_service._weather_cache[cache_key("Казань", 55.8, 49.1)] = (1.5, datetime.now())

        class _Client:
            def __init__(self, *args, **kwargs) -> None:
                raise AssertionError("network should not be called")

        with unittest.mock.patch("services.weather_service.httpx.AsyncClient", _Client):
            temp = await get_current_temperature(55.8, 49.1, city="Казань")
        self.assertEqual(temp, 1.5)

    async def test_no_weather_says_so_and_still_returns_a_season(self) -> None:
        with unittest.mock.patch(
            "bot.storage.get_user_location",
            new=AsyncMock(return_value=("Москва", None, None)),
        ), unittest.mock.patch(
            "services.weather_service.get_current_temperature",
            new=AsyncMock(return_value=None),
        ):
            season, message = await detect_season_for_user(5)
        self.assertIn(season, {"winter", "demi", "summer"})
        self.assertIn("Погоду уточнить не удалось", message)

    async def test_background_refresh_fills_city_cache_every_half_hour(self) -> None:
        from services import weather_service

        clear_weather_cache()
        places = [{"city": "Сочи", "lat": 43.6, "lon": 39.7}]
        with unittest.mock.patch(
            "bot.storage.list_weather_places",
            new=AsyncMock(return_value=places),
        ), unittest.mock.patch(
            "services.weather_service.get_current_temperature",
            new=AsyncMock(return_value=18.0),
        ) as fetch:
            self.assertTrue(await maybe_refresh_active_cities(datetime.now()))
            fetch.assert_awaited()
            self.assertFalse(await maybe_refresh_active_cities(datetime.now()))
            self.assertEqual(fetch.await_count, 1)
        weather_service._last_refresh_at = datetime.now() - timedelta(minutes=31)
        with unittest.mock.patch(
            "bot.storage.list_weather_places",
            new=AsyncMock(return_value=places),
        ), unittest.mock.patch(
            "services.weather_service.get_current_temperature",
            new=AsyncMock(return_value=19.0),
        ) as fetch_again:
            self.assertTrue(await maybe_refresh_active_cities(datetime.now()))
        fetch_again.assert_awaited()


if __name__ == "__main__":
    unittest.main()
