import unittest

from bot.storage import (
    add_item,
    clear_user_items,
    delete_item,
    delete_item_by_id,
    get_items,
    init_storage,
    update_display_name,
    update_item_metadata,
    update_processed_file_id,
)


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await init_storage()

    async def test_delete_item_by_id_removes_selected_entry(self) -> None:
        user_id = 910001
        await clear_user_items(user_id)
        first_id = await add_item(user_id=user_id, category="top", telegram_file_id="top-1")
        await add_item(user_id=user_id, category="shoes", telegram_file_id="shoes-1")

        removed = await delete_item_by_id(user_id=user_id, item_id=first_id)

        self.assertIsNotNone(removed)
        self.assertEqual(removed["telegram_file_id"], "top-1")
        remaining = await get_items(user_id)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["telegram_file_id"], "shoes-1")

    async def test_delete_item_by_id_returns_none_for_invalid_id(self) -> None:
        user_id = 910002
        await clear_user_items(user_id)
        await add_item(user_id=user_id, category="top", telegram_file_id="top-2")

        removed = await delete_item_by_id(user_id=user_id, item_id=999_999)

        self.assertIsNone(removed)
        self.assertEqual(len(await get_items(user_id)), 1)

    async def test_backward_compatible_delete_item_by_index(self) -> None:
        user_id = 910004
        await clear_user_items(user_id)
        await add_item(user_id=user_id, category="top", telegram_file_id="top-4")
        await add_item(user_id=user_id, category="shoes", telegram_file_id="shoes-4")

        removed = await delete_item(user_id=user_id, item_index=1)

        self.assertIsNotNone(removed)
        self.assertEqual(removed["telegram_file_id"], "shoes-4")
        remaining = await get_items(user_id)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["telegram_file_id"], "top-4")

    async def test_update_fields_and_metadata(self) -> None:
        user_id = 910003
        await clear_user_items(user_id)
        item_id = await add_item(user_id=user_id, category="top", telegram_file_id="top-3")

        self.assertTrue(await update_processed_file_id(user_id=user_id, item_id=item_id, file_id="processed-3"))
        self.assertTrue(await update_display_name(user_id=user_id, item_id=item_id, display_name="Серая футболка"))
        self.assertTrue(
            await update_item_metadata(
                user_id=user_id,
                item_id=item_id,
                metadata={"type": "t-shirt", "primary_color": "gray"},
            )
        )

        item = (await get_items(user_id))[0]
        self.assertEqual(item["processed_file_id"], "processed-3")
        self.assertEqual(item["display_name"], "Серая футболка")
        self.assertEqual(item["type"], "t-shirt")
        self.assertEqual(item["primary_color"], "gray")


if __name__ == "__main__":
    unittest.main()
