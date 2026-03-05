import unittest
from unittest.mock import MagicMock, patch

from services.outfit_service import OutfitImageService


class _FakeComposedImage:
    def save(self, buffer, format="PNG") -> None:
        buffer.write(b"fake-png-bytes")


class OutfitImageServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_render_outfit_image_uses_real_user_photos(self) -> None:
        service = OutfitImageService()
        fake_downloaded_image = object()

        async def fake_download(bot, file_id):
            return fake_downloaded_image if file_id == "top-1" else None

        with (
            patch.object(service, "_download_image", side_effect=fake_download),
            patch.object(service, "_compose_outfit", return_value=_FakeComposedImage()) as compose_mock,
        ):
            result = await service.render_outfit_image(
                bot=object(),
                items_payload={"top": ["top-1"]},
            )

        self.assertEqual(result, b"fake-png-bytes")
        compose_mock.assert_called_once()

    async def test_render_outfit_image_returns_none_if_no_downloaded_images(self) -> None:
        service = OutfitImageService()

        async def fake_download(bot, file_id):
            return None

        with patch.object(service, "_download_image", side_effect=fake_download):
            result = await service.render_outfit_image(
                bot=object(),
                items_payload={"top": ["top-1"]},
            )

        self.assertIsNone(result)


class ComposeOutfitTemplateSelectionTests(unittest.TestCase):
    """Tests for auto template selection in _compose_outfit."""

    def _fake_image(self):
        return object()

    def test_selects_outerwear_template_when_outerwear_present(self) -> None:
        category_images = {
            "outerwear": self._fake_image(),
            "top": self._fake_image(),
            "bottom": self._fake_image(),
            "shoes": self._fake_image(),
        }
        with patch("services.outfit_service.PhotoTemplateService.compose") as compose_mock:
            compose_mock.return_value = MagicMock()
            OutfitImageService._compose_outfit(category_images)

        _, kwargs = compose_mock.call_args
        self.assertEqual(kwargs.get("template_name"), "outfit_story_outerwear")

    def test_selects_standard_template_when_no_outerwear(self) -> None:
        category_images = {
            "top": self._fake_image(),
            "bottom": self._fake_image(),
            "shoes": self._fake_image(),
        }
        with patch("services.outfit_service.PhotoTemplateService.compose") as compose_mock:
            compose_mock.return_value = MagicMock()
            OutfitImageService._compose_outfit(category_images)

        _, kwargs = compose_mock.call_args
        self.assertEqual(kwargs.get("template_name"), "outfit_story")

    def test_dress_outfit_without_outerwear_uses_standard_template(self) -> None:
        category_images = {
            "dress": self._fake_image(),
            "shoes": self._fake_image(),
        }
        with patch("services.outfit_service.PhotoTemplateService.compose") as compose_mock:
            compose_mock.return_value = MagicMock()
            OutfitImageService._compose_outfit(category_images)

        _, kwargs = compose_mock.call_args
        self.assertEqual(kwargs.get("template_name"), "outfit_story")


if __name__ == "__main__":
    unittest.main()
