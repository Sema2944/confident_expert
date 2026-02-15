cat > tests/test_photo_template_service.py <<'PY'
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


if __name__ == "__main__":
    unittest.main()
PY
