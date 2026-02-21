import unittest

from services.fashion_trend_service import FashionTrendService


class FashionTrendServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_fallback_contains_russian_insights(self) -> None:
        digest = FashionTrendService._fallback_trends(season="winter", year=2026)

        self.assertIn("Тренды", digest)
        self.assertIn("Vogue", digest)
        self.assertIn("Who What Wear", digest)
        self.assertIn("Где следить за трендами", digest)

    def test_fallback_uses_season_label(self) -> None:
        digest = FashionTrendService._fallback_trends(season="summer", year=2026)
        self.assertIn("лето", digest)

    def test_fallback_uses_year(self) -> None:
        digest = FashionTrendService._fallback_trends(season="all", year=2025)
        self.assertIn("2025", digest)

    async def test_get_trend_digest_returns_fallback_without_api_key(self) -> None:
        service = FashionTrendService()
        digest = await service.get_trend_digest(season="winter", year=2026)
        self.assertIn("Тренды", digest)
        self.assertIsInstance(digest, str)
        self.assertTrue(len(digest) > 50)


if __name__ == "__main__":
    unittest.main()
