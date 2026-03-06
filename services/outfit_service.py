from io import BytesIO

from services.photo_template_service import PhotoTemplateService


class OutfitImageService:
    _CATEGORY_ORDER = ["top", "bottom", "dress", "outerwear", "shoes", "accessories"]

    async def render_outfit_image(
        self,
        bot,
        items_payload: dict[str, list[str]],
        template_name: str = "outfit_story",
        photo_urls: dict[str, str] | None = None,
    ) -> bytes | None:
        category_images: dict[str, object] = {}
        for category in self._CATEGORY_ORDER:
            file_ids = items_payload.get(category, [])
            for file_id in file_ids:
                photo_url = (photo_urls or {}).get(file_id)
                image = await self._download_image(bot=bot, file_id=file_id, photo_url=photo_url)
                if image is not None:
                    category_images[category] = image
                    break

        if not category_images:
            return None

        composed = self._compose_outfit(category_images, template_name=template_name)
        buffer = BytesIO()
        composed.save(buffer, format="PNG")
        return buffer.getvalue()

    async def _download_image(self, bot, file_id: str, photo_url: str | None = None):
        from PIL import Image
        import httpx

        # Try S3/URL first if available
        if photo_url:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(photo_url)
                    resp.raise_for_status()
                    content = BytesIO(resp.content)
                    image = Image.open(content)
                    image.load()
                    return image.convert("RGB")
            except Exception:
                pass  # fallback to Telegram

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
