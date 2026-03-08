import logging
from io import BytesIO

from services.photo_template_service import PhotoTemplateService

logger = logging.getLogger(__name__)


class OutfitImageService:
    _CATEGORY_ORDER = ["top", "bottom", "dress", "outerwear", "shoes", "accessories"]

    async def render_outfit_image(
        self,
        bot,
        items_payload: dict[str, list[str]],
        template_name: str = "outfit_story",
        s3_items: dict[str, tuple[int, int]] | None = None,
    ) -> bytes | None:
        category_images: dict[str, object] = {}
        for category in self._CATEGORY_ORDER:
            file_ids = items_payload.get(category, [])
            for file_id in file_ids:
                s3_info = (s3_items or {}).get(file_id)
                user_id = s3_info[0] if s3_info else None
                item_id = s3_info[1] if s3_info else None
                image = await self._download_image(
                    bot=bot, file_id=file_id,
                    user_id=user_id, item_id=item_id,
                )
                if image is not None:
                    category_images[category] = image
                    break

        if not category_images:
            return None

        composed = self._compose_outfit(category_images, template_name=template_name)
        buffer = BytesIO()
        composed.save(buffer, format="PNG")
        return buffer.getvalue()

    async def _download_image(
        self, bot, file_id: str,
        user_id: int | None = None, item_id: int | None = None,
    ):
        from PIL import Image

        # Try S3 via authorized boto3 first
        if user_id is not None and item_id is not None:
            try:
                from services.s3_storage_service import s3_service
                photo_bytes = s3_service.get_photo(user_id, item_id)
                if photo_bytes:
                    image = Image.open(BytesIO(photo_bytes))
                    image.load()
                    return image.convert("RGB")
            except Exception:
                logger.debug("S3 download failed for user=%s item=%s, falling back to Telegram", user_id, item_id)

        # Fallback to Telegram file_id
        try:
            telegram_file = await bot.get_file(file_id)
            content = BytesIO()
            await bot.download_file(telegram_file.file_path, destination=content)
            content.seek(0)
            image = Image.open(content)
            image.load()
            return image.convert("RGB")
        except Exception:
            return None

    @staticmethod
    def _compose_outfit(category_images, template_name: str = "outfit_story"):
        # Auto-select layout based on outfit composition
        if "outerwear" in category_images:
            template_name = "outfit_story_outerwear"
        else:
            template_name = "outfit_story"

        template_images = {}
        if category_images.get("dress") is not None:
            template_images["dress"] = category_images["dress"]
        else:
            if category_images.get("outerwear") is not None:
                template_images["outerwear"] = category_images["outerwear"]
            if category_images.get("top") is not None:
                template_images["top"] = category_images["top"]
            if category_images.get("bottom") is not None:
                template_images["bottom"] = category_images["bottom"]

        if category_images.get("shoes") is not None:
            template_images["shoes"] = category_images["shoes"]

        if category_images.get("accessories") is not None:
            template_images["accessories"] = category_images["accessories"]

        return PhotoTemplateService.compose(template_images, template_name=template_name)
