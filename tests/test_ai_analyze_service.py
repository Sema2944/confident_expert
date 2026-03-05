import unittest

from services.ai_analyze_service import AIAnalyzeService, ItemAnalysis


class ItemAnalysisPhotoQualityTests(unittest.TestCase):
    """Tests for photo_quality field in ItemAnalysis."""

    def setUp(self):
        self.service = AIAnalyzeService()

    def test_item_analysis_has_photo_quality_field(self) -> None:
        analysis = ItemAnalysis()
        self.assertIsNone(analysis.photo_quality)

    def test_parse_good_photo_quality(self) -> None:
        payload = {
            "type": "t-shirt",
            "primary_color": "gray",
            "secondary_color": "unknown",
            "pattern": "solid",
            "season": "all",
            "formality": "casual",
            "gender_hint": "unisex",
            "photo_quality": "good",
        }
        analysis = self.service._parse_analysis(payload)
        self.assertEqual(analysis.photo_quality, "good")

    def test_parse_poor_photo_quality(self) -> None:
        payload = {"photo_quality": "poor"}
        analysis = self.service._parse_analysis(payload)
        self.assertEqual(analysis.photo_quality, "poor")

    def test_parse_unclear_photo_quality(self) -> None:
        payload = {"photo_quality": "unclear"}
        analysis = self.service._parse_analysis(payload)
        self.assertEqual(analysis.photo_quality, "unclear")

    def test_parse_invalid_photo_quality_falls_back_to_unknown(self) -> None:
        payload = {"photo_quality": "garbage_value"}
        analysis = self.service._parse_analysis(payload)
        self.assertEqual(analysis.photo_quality, "unknown")

    def test_parse_missing_photo_quality_falls_back_to_unknown(self) -> None:
        payload = {"type": "jeans"}
        analysis = self.service._parse_analysis(payload)
        self.assertEqual(analysis.photo_quality, "unknown")

    def test_unknown_analysis_has_good_photo_quality(self) -> None:
        """Technical failure should not block upload — photo_quality stays 'good'."""
        analysis = AIAnalyzeService._unknown_analysis()
        self.assertEqual(analysis.photo_quality, "good")

    def test_photo_quality_values_set_contains_expected(self) -> None:
        self.assertIn("good", AIAnalyzeService._PHOTO_QUALITY_VALUES)
        self.assertIn("poor", AIAnalyzeService._PHOTO_QUALITY_VALUES)
        self.assertIn("unclear", AIAnalyzeService._PHOTO_QUALITY_VALUES)


if __name__ == "__main__":
    unittest.main()
