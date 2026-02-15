import unittest

from services.fashion_trend_service import FashionTrendService


class FashionTrendServiceTests(unittest.TestCase):
    def test_fallback_replaces_english_headlines_with_clear_insights(self) -> None:
        signals = [
            "https://www.vogue.com/feed/rss :: Dua Lipa and Callum Turner Take Opposite Couples Style to the Extreme in Berlin",
            "https://www.whowhatwear.com/rss :: H&M's Expensive-Looking Cardigan Sold Out Instantly Last Year—Now It's Back In a Chicer Shade",
        ]

        digest = FashionTrendService._fallback_trends(season="зима", year=2026, source_signals=signals)

        self.assertIn("Vogue: акцент на носибельную многослойность", digest)
        self.assertIn("Who What Wear: ставка на трендовые оттенки", digest)
        self.assertIn("Где следить за трендами на русском", digest)
        self.assertNotIn("Dua Lipa", digest)
        self.assertNotIn("Cardigan", digest)

    def test_localize_signal_keeps_russian_headline_without_noise(self) -> None:
        signal = "https://www.vogue.com/feed/rss :: Модный дом показал новую зимнюю коллекцию"

        localized = FashionTrendService._localize_signal_for_russian(signal)

        self.assertEqual(localized, "Vogue: Модный дом показал новую зимюю коллекцию")

    def test_localize_signal_clarifies_accent_accessories(self) -> None:
        signal = "https://www.harpersbazaar.com/rss/all.xml :: Модные дома возвращают акцентные аксессуары"

        localized = FashionTrendService._localize_signal_for_russian(signal)

        self.assertIn("крупные серьги, широкие ремни и заметные сумки", localized)


if __name__ == "__main__":
    unittest.main()
