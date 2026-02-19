import unittest

from bot.storage import (
    add_item,
    clear_user_items,
    delete_item,
    delete_item_by_id,
    get_items,
    update_display_name,
    update_item_metadata,
    update_processed_file_id,
)


class StorageTests(unittest.TestCase):
    def test_delete_item_by_id_removes_selected_entry(self) -> None:
        user_id = 910001
        clear_user_items(user_id)
        first_id = add_item(user_id=user_id, category="top", telegram_file_id="top-1")
        add_item(user_id=user_id, category="shoes", telegram_file_id="shoes-1")

        removed = delete_item_by_id(user_id=user_id, item_id=first_id)

        self.assertIsNotNone(removed)
        self.assertEqual(removed["telegram_file_id"], "top-1")
        remaining = get_items(user_id)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["telegram_file_id"], "shoes-1")

    def test_delete_item_by_id_returns_none_for_invalid_id(self) -> None:
        user_id = 910002
        clear_user_items(user_id)
        add_item(user_id=user_id, category="top", telegram_file_id="top-2")

        removed = delete_item_by_id(user_id=user_id, item_id=999_999)

        self.assertIsNone(removed)
        self.assertEqual(len(get_items(user_id)), 1)


    def test_backward_compatible_delete_item_by_index(self) -> None:
        user_id = 910004
        clear_user_items(user_id)
        add_item(user_id=user_id, category="top", telegram_file_id="top-4")
        add_item(user_id=user_id, category="shoes", telegram_file_id="shoes-4")

        removed = delete_item(user_id=user_id, item_index=1)

        self.assertIsNotNone(removed)
        self.assertEqual(removed["telegram_file_id"], "shoes-4")
        remaining = get_items(user_id)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["telegram_file_id"], "top-4")

    def test_update_fields_and_metadata(self) -> None:
        user_id = 910003
        clear_user_items(user_id)
        item_id = add_item(user_id=user_id, category="top", telegram_file_id="top-3")

        self.assertTrue(update_processed_file_id(user_id=user_id, item_id=item_id, file_id="processed-3"))
        self.assertTrue(update_display_name(user_id=user_id, item_id=item_id, display_name="Серая футболка"))
        self.assertTrue(
            update_item_metadata(
                user_id=user_id,
                item_id=item_id,
                metadata={"type": "t-shirt", "primary_color": "gray"},
            )
        )

        item = get_items(user_id)[0]
        self.assertEqual(item["processed_file_id"], "processed-3")
        self.assertEqual(item["display_name"], "Серая футболка")
        self.assertEqual(item["type"], "t-shirt")
        self.assertEqual(item["primary_color"], "gray")


if __name__ == "__main__":
    unittest.main()
