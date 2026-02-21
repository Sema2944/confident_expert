import unittest

from services.outfit_generation_service import (
    OutfitService,
    _color_compatibility_score,
    _filter_items_for_context,
)


class OutfitGenerationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_generates_outfit_with_legacy_category_names(self) -> None:
        service = OutfitService()
        items = [
            {"category": "tops", "telegram_file_id": "top-1"},
            {"category": "bottoms", "telegram_file_id": "bottom-1"},
            {"category": "shoe", "telegram_file_id": "shoe-1"},
            {"category": "accessories", "telegram_file_id": "acc-1"},
        ]

        outfits = await service.generate_outfits(items=items, occasion="work_office", season="all", count=1)

        self.assertEqual(len(outfits), 1)
        self.assertEqual(outfits[0].items["top"], ["top-1"])
        self.assertEqual(outfits[0].items["bottom"], ["bottom-1"])
        self.assertEqual(outfits[0].items["shoes"], ["shoe-1"])
        self.assertEqual(outfits[0].items["accessories"], ["acc-1"])

    async def test_generates_outfit_with_russian_category_names(self) -> None:
        service = OutfitService()
        items = [
            {"category": "платье", "telegram_file_id": "dress-1"},
            {"category": "обувь", "telegram_file_id": "shoe-1"},
        ]

        outfits = await service.generate_outfits(items=items, occasion="going_out", season="all", count=1)

        self.assertEqual(len(outfits), 1)
        self.assertEqual(outfits[0].items["dress"], ["dress-1"])
        self.assertEqual(outfits[0].items["shoes"], ["shoe-1"])

    async def test_prefers_processed_file_id_for_payload(self) -> None:
        service = OutfitService()
        items = [
            {"category": "top", "telegram_file_id": "top-raw", "processed_file_id": "top-processed"},
            {"category": "bottom", "telegram_file_id": "bottom-raw"},
            {"category": "shoes", "telegram_file_id": "shoes-raw", "processed_file_id": "shoes-processed"},
        ]

        outfits = await service.generate_outfits(items=items, occasion="casual", season="all", count=1)

        self.assertEqual(len(outfits), 1)
        self.assertEqual(outfits[0].items["top"], ["top-processed"])
        self.assertEqual(outfits[0].items["bottom"], ["bottom-raw"])
        self.assertEqual(outfits[0].items["shoes"], ["shoes-processed"])


class FilterItemsTests(unittest.TestCase):
    def _make_item(self, category: str, season: str = "all", formality: str = "casual") -> dict:
        return {"category": category, "season": season, "formality": formality, "telegram_file_id": f"{category}-1"}

    def test_winter_excludes_summer_items(self) -> None:
        items = [
            self._make_item("top", season="summer"),
            self._make_item("top", season="winter"),
            self._make_item("bottom", season="all"),
            self._make_item("shoes", season="all"),
        ]
        filtered = _filter_items_for_context(items, occasion="casual", season="winter")
        seasons = {i["season"] for i in filtered if i["category"] == "top"}
        self.assertNotIn("summer", seasons)
        self.assertIn("winter", seasons)

    def test_summer_excludes_winter_items(self) -> None:
        items = [
            self._make_item("top", season="winter"),
            self._make_item("top", season="summer"),
            self._make_item("bottom", season="summer"),
            self._make_item("shoes", season="all"),
        ]
        filtered = _filter_items_for_context(items, occasion="casual", season="summer")
        seasons = {i["season"] for i in filtered if i["category"] == "top"}
        self.assertNotIn("winter", seasons)
        self.assertIn("summer", seasons)

    def test_work_office_excludes_sport(self) -> None:
        items = [
            self._make_item("top", formality="sport"),
            self._make_item("top", formality="office"),
            self._make_item("bottom", formality="office"),
            self._make_item("shoes", formality="casual"),
        ]
        filtered = _filter_items_for_context(items, occasion="work_office", season="all")
        formalities = {i["formality"] for i in filtered if i["category"] == "top"}
        self.assertNotIn("sport", formalities)
        self.assertIn("office", formalities)

    def test_fallback_adds_required_categories_if_missing(self) -> None:
        items = [
            self._make_item("top", season="summer"),
            self._make_item("bottom", season="summer"),
            self._make_item("shoes", season="summer"),
        ]
        # Winter filter would exclude all summer items, but fallback adds required categories back
        filtered = _filter_items_for_context(items, occasion="casual", season="winter")
        categories = {i["category"] for i in filtered}
        self.assertIn("top", categories)
        self.assertIn("shoes", categories)

    def test_all_season_passes_everything(self) -> None:
        items = [
            self._make_item("top", season="winter"),
            self._make_item("top", season="summer"),
            self._make_item("bottom", season="demi"),
            self._make_item("shoes", season="all"),
        ]
        filtered = _filter_items_for_context(items, occasion="casual", season="all")
        self.assertEqual(len(filtered), len(items))


class ColorScoringTests(unittest.TestCase):
    def test_all_neutral_scores_perfect(self) -> None:
        items = [
            {"primary_color": "black"},
            {"primary_color": "white"},
            {"primary_color": "gray"},
        ]
        self.assertEqual(_color_compatibility_score(items), 1.0)

    def test_neutral_plus_one_accent_scores_well(self) -> None:
        items = [
            {"primary_color": "black"},
            {"primary_color": "white"},
            {"primary_color": "red"},
        ]
        self.assertEqual(_color_compatibility_score(items), 1.0)

    def test_monochrome_accent_scores_high(self) -> None:
        items = [
            {"primary_color": "red"},
            {"primary_color": "red"},
        ]
        self.assertGreaterEqual(_color_compatibility_score(items), 0.9)

    def test_many_different_accents_scores_low(self) -> None:
        items = [
            {"primary_color": "red"},
            {"primary_color": "green"},
            {"primary_color": "purple"},
        ]
        self.assertLessEqual(_color_compatibility_score(items), 0.4)

    def test_single_item_scores_perfect(self) -> None:
        self.assertEqual(_color_compatibility_score([{"primary_color": "red"}]), 1.0)

    def test_unknown_colors_ignored(self) -> None:
        items = [
            {"primary_color": "unknown"},
            {"primary_color": "black"},
        ]
        self.assertEqual(_color_compatibility_score(items), 1.0)


if __name__ == "__main__":
    unittest.main()
