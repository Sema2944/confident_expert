import unittest

from services.outfit_generation_service import OutfitService


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


if __name__ == "__main__":
    unittest.main()
