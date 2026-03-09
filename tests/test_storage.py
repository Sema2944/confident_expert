import unittest

from bot.storage import (
    add_item,
    add_item_to_capsule,
    clear_user_items,
    create_capsule,
    delete_capsule,
    delete_item,
    delete_item_by_id,
    get_capsule_items,
    get_items,
    get_user_capsules,
    init_storage,
    remove_item_from_capsule,
    rename_capsule,
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


    async def test_create_capsule_and_list(self) -> None:
        user_id = 920001
        capsule_id = await create_capsule(user_id, "Офис", "🏢")
        self.assertIsInstance(capsule_id, int)
        self.assertGreater(capsule_id, 0)

        capsules = await get_user_capsules(user_id)
        self.assertTrue(any(c["name"] == "Офис" for c in capsules))

    async def test_add_and_remove_item_from_capsule(self) -> None:
        user_id = 920002
        await clear_user_items(user_id)
        item_id = await add_item(user_id=user_id, category="top", telegram_file_id="cap-top-1")
        capsule_id = await create_capsule(user_id, "Тест", "🧪")

        added = await add_item_to_capsule(capsule_id, item_id)
        self.assertTrue(added)

        items = await get_capsule_items(user_id, capsule_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["telegram_file_id"], "cap-top-1")

        # Duplicate add returns False
        added2 = await add_item_to_capsule(capsule_id, item_id)
        self.assertFalse(added2)

        await remove_item_from_capsule(capsule_id, item_id)
        items_after = await get_capsule_items(user_id, capsule_id)
        self.assertEqual(len(items_after), 0)

    async def test_delete_capsule(self) -> None:
        user_id = 920003
        capsule_id = await create_capsule(user_id, "Удалить", "🗑")
        deleted = await delete_capsule(user_id, capsule_id)
        self.assertTrue(deleted)
        capsules = await get_user_capsules(user_id)
        self.assertFalse(any(c["id"] == capsule_id for c in capsules))

    async def test_delete_capsule_wrong_user(self) -> None:
        user_id = 920004
        capsule_id = await create_capsule(user_id, "Чужая", "🔒")
        deleted = await delete_capsule(999999, capsule_id)
        self.assertFalse(deleted)

    async def test_rename_capsule(self) -> None:
        user_id = 920005
        capsule_id = await create_capsule(user_id, "Старое", "📝")
        await rename_capsule(user_id, capsule_id, "Новое")
        capsules = await get_user_capsules(user_id)
        cap = next(c for c in capsules if c["id"] == capsule_id)
        self.assertEqual(cap["name"], "Новое")


if __name__ == "__main__":
    unittest.main()
