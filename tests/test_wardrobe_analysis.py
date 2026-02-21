import unittest

from services.wardrobe_analysis_service import analyze_wardrobe_gaps


class WardrobeAnalysisTests(unittest.TestCase):
    def test_returns_none_for_empty_list(self) -> None:
        self.assertIsNone(analyze_wardrobe_gaps([]))

    def test_warns_no_shoes(self) -> None:
        items = [
            {"category": "top", "season": "all", "formality": "casual"},
            {"category": "bottom", "season": "all", "formality": "casual"},
        ]
        result = analyze_wardrobe_gaps(items)
        self.assertIsNotNone(result)
        self.assertIn("обувь", result)

    def test_warns_no_top(self) -> None:
        items = [
            {"category": "shoes", "season": "all", "formality": "casual"},
            {"category": "bottom", "season": "all", "formality": "casual"},
        ]
        result = analyze_wardrobe_gaps(items)
        self.assertIsNotNone(result)
        self.assertIn("верх", result.lower())

    def test_warns_no_bottom(self) -> None:
        items = [
            {"category": "top", "season": "all", "formality": "casual"},
            {"category": "shoes", "season": "all", "formality": "casual"},
        ]
        result = analyze_wardrobe_gaps(items)
        self.assertIsNotNone(result)
        self.assertIn("брюки", result.lower())

    def test_onepiece_satisfies_top_and_bottom(self) -> None:
        items = [
            {"category": "onepiece", "season": "all", "formality": "casual"},
            {"category": "shoes", "season": "all", "formality": "casual"},
            {"category": "accessory", "season": "all", "formality": "casual"},
        ]
        result = analyze_wardrobe_gaps(items)
        # No "верх" or "низ" warnings because onepiece covers them
        if result:
            self.assertNotIn("верх", result.lower())
            self.assertNotIn("брюки", result.lower())

    def test_warns_few_items(self) -> None:
        items = [{"category": "top", "season": "all", "formality": "casual"}]
        result = analyze_wardrobe_gaps(items)
        self.assertIsNotNone(result)
        self.assertIn("мало", result)

    def test_warns_single_season(self) -> None:
        items = [
            {"category": "top", "season": "winter", "formality": "casual"},
            {"category": "bottom", "season": "winter", "formality": "office"},
            {"category": "shoes", "season": "winter", "formality": "casual"},
            {"category": "outerwear", "season": "winter", "formality": "casual"},
        ]
        result = analyze_wardrobe_gaps(items)
        self.assertIsNotNone(result)
        self.assertIn("сезон", result.lower())

    def test_warns_single_formality(self) -> None:
        items = [
            {"category": "top", "season": "summer", "formality": "sport"},
            {"category": "bottom", "season": "winter", "formality": "sport"},
            {"category": "shoes", "season": "all", "formality": "sport"},
            {"category": "outerwear", "season": "demi", "formality": "sport"},
        ]
        result = analyze_wardrobe_gaps(items)
        self.assertIsNotNone(result)
        self.assertIn("стиля", result.lower())

    def test_warns_no_accessories_when_many_items(self) -> None:
        items = [
            {"category": "top", "season": "summer", "formality": "casual"},
            {"category": "top", "season": "winter", "formality": "office"},
            {"category": "top", "season": "demi", "formality": "smart"},
            {"category": "bottom", "season": "summer", "formality": "casual"},
            {"category": "bottom", "season": "winter", "formality": "office"},
            {"category": "bottom", "season": "demi", "formality": "smart"},
            {"category": "shoes", "season": "all", "formality": "casual"},
            {"category": "shoes", "season": "winter", "formality": "office"},
            {"category": "outerwear", "season": "winter", "formality": "casual"},
            {"category": "outerwear", "season": "demi", "formality": "office"},
            {"category": "onepiece", "season": "summer", "formality": "smart"},
        ]
        result = analyze_wardrobe_gaps(items)
        self.assertIsNotNone(result)
        self.assertIn("аксессуар", result.lower())

    def test_returns_none_for_well_balanced_wardrobe(self) -> None:
        items = [
            {"category": "top", "season": "summer", "formality": "casual"},
            {"category": "top", "season": "winter", "formality": "office"},
            {"category": "bottom", "season": "summer", "formality": "casual"},
            {"category": "bottom", "season": "winter", "formality": "office"},
            {"category": "shoes", "season": "all", "formality": "casual"},
            {"category": "outerwear", "season": "winter", "formality": "casual"},
            {"category": "accessory", "season": "all", "formality": "casual"},
        ]
        result = analyze_wardrobe_gaps(items)
        self.assertIsNone(result)

    def test_max_two_hints(self) -> None:
        items = [{"category": "accessory", "season": "unknown", "formality": "unknown"}]
        result = analyze_wardrobe_gaps(items)
        self.assertIsNotNone(result)
        lines = [line for line in result.split("\n") if line.strip()]
        self.assertLessEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main()
