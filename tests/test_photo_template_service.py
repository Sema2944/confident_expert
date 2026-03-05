import unittest

from services.photo_template_service import PhotoTemplateService


class PhotoTemplateServiceTests(unittest.TestCase):
    def test_lists_available_templates(self) -> None:
        templates = PhotoTemplateService.available_templates()

        self.assertIn("outfit_story", templates)
        self.assertIn("grid_2x2", templates)

    def test_get_outfit_story_template_settings(self) -> None:
        template = PhotoTemplateService.get_template("outfit_story")

        self.assertEqual(template.canvas_width, 1536)
        self.assertEqual(template.canvas_height, 2304)
        self.assertIn("dress", template.slots)
        self.assertIn("shoes", template.slots)

    def test_unknown_template_raises_error(self) -> None:
        with self.assertRaises(ValueError):
            PhotoTemplateService.get_template("unknown")

    def test_lists_available_templates_includes_outerwear_layout(self) -> None:
        templates = PhotoTemplateService.available_templates()

        self.assertIn("outfit_story_outerwear", templates)

    def test_get_outfit_story_outerwear_template_settings(self) -> None:
        template = PhotoTemplateService.get_template("outfit_story_outerwear")

        self.assertEqual(template.canvas_width, 1800)
        self.assertEqual(template.canvas_height, 2304)
        self.assertIn("outerwear", template.slots)
        self.assertIn("top", template.slots)
        self.assertIn("bottom", template.slots)
        self.assertIn("shoes", template.slots)
        self.assertIn("accessories", template.slots)

    def test_outerwear_slot_is_on_the_left(self) -> None:
        template = PhotoTemplateService.get_template("outfit_story_outerwear")
        outerwear_slot = template.slots["outerwear"]
        top_slot = template.slots["top"]

        # outerwear x should be less than top x (outerwear is on the left)
        self.assertLess(outerwear_slot.x, top_slot.x)

    def test_outerwear_slot_is_wider_than_right_column_items(self) -> None:
        template = PhotoTemplateService.get_template("outfit_story_outerwear")
        outerwear_slot = template.slots["outerwear"]
        top_slot = template.slots["top"]

        # outerwear is the dominant item — wider than top
        self.assertGreater(outerwear_slot.width, top_slot.width)


if __name__ == "__main__":
    unittest.main()
