import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
