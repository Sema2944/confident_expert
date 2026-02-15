import unittest

from bot.storage import add_item, delete_item, get_items


class StorageTests(unittest.TestCase):
    def test_delete_item_removes_selected_entry(self) -> None:
        user_id = 910001
        add_item(user_id=user_id, category="top", telegram_file_id="top-1")
        add_item(user_id=user_id, category="shoes", telegram_file_id="shoes-1")

        removed = delete_item(user_id=user_id, item_index=0)

        self.assertIsNotNone(removed)
        self.assertEqual(removed["telegram_file_id"], "top-1")
        remaining = get_items(user_id)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["telegram_file_id"], "shoes-1")

    def test_delete_item_returns_none_for_invalid_index(self) -> None:
        user_id = 910002
        add_item(user_id=user_id, category="top", telegram_file_id="top-2")

        removed = delete_item(user_id=user_id, item_index=99)

        self.assertIsNone(removed)
        self.assertEqual(len(get_items(user_id)), 1)


if __name__ == "__main__":
    unittest.main()
