import unittest

from config.categories import CATEGORIES, CATEGORY_ALIASES, CATEGORY_LABELS_RU, normalize_category


class CategoriesTests(unittest.TestCase):
    def test_all_canonical_categories_have_labels(self) -> None:
        for cat in CATEGORIES:
            self.assertIn(cat, CATEGORY_LABELS_RU, f"Missing label for category: {cat}")

    def test_all_canonical_categories_self_normalize(self) -> None:
        for cat in CATEGORIES:
            self.assertEqual(normalize_category(cat), cat)

    def test_russian_aliases_resolve(self) -> None:
        self.assertEqual(normalize_category("верх"), "top")
        self.assertEqual(normalize_category("👕 верх"), "top")
        self.assertEqual(normalize_category("низ"), "bottom")
        self.assertEqual(normalize_category("👖 низ"), "bottom")
        self.assertEqual(normalize_category("верхняя одежда"), "outerwear")
        self.assertEqual(normalize_category("обувь"), "shoes")
        self.assertEqual(normalize_category("аксессуары"), "accessory")
        self.assertEqual(normalize_category("платье"), "onepiece")
        self.assertEqual(normalize_category("цельный образ"), "onepiece")

    def test_english_aliases_resolve(self) -> None:
        self.assertEqual(normalize_category("tops"), "top")
        self.assertEqual(normalize_category("bottoms"), "bottom")
        self.assertEqual(normalize_category("shoe"), "shoes")
        self.assertEqual(normalize_category("accessories"), "accessory")
        self.assertEqual(normalize_category("dress"), "onepiece")
        self.assertEqual(normalize_category("dresses"), "onepiece")

    def test_case_insensitive(self) -> None:
        self.assertEqual(normalize_category("TOP"), "top")
        self.assertEqual(normalize_category("Верх"), "top")
        self.assertEqual(normalize_category("SHOES"), "shoes")

    def test_whitespace_stripped(self) -> None:
        self.assertEqual(normalize_category("  top  "), "top")
        self.assertEqual(normalize_category(" верх "), "top")

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(normalize_category("laptop"))
        self.assertIsNone(normalize_category(""))
        self.assertIsNone(normalize_category("  "))

    def test_none_input_returns_none(self) -> None:
        self.assertIsNone(normalize_category(None))

    def test_all_aliases_point_to_canonical_categories(self) -> None:
        for alias, target in CATEGORY_ALIASES.items():
            self.assertIn(target, CATEGORIES, f"Alias '{alias}' points to non-canonical category '{target}'")


if __name__ == "__main__":
    unittest.main()
