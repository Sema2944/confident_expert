from io import BytesIO

from services.outfit_generation_service import OutfitResult, OutfitService


class OutfitImageService:
    _CATEGORY_ORDER = ["top", "bottom", "dress", "outerwear", "shoes", "accessories"]

    async def render_outfit_image(self, bot, items_payload: dict[str, list[str]]) -> bytes | None:
        from PIL import Image

        category_images: dict[str, Image.Image] = {}
        for category in self._CATEGORY_ORDER:
            file_ids = items_payload.get(category, [])
            for file_id in file_ids:
                image = await self._download_image(bot=bot, file_id=file_id)
                if image is not None:
                    category_images[category] = image
                    break

        if not category_images:
            return None

        composed = self._compose_outfit(category_images)
        buffer = BytesIO()
        composed.save(buffer, format="PNG")
        return buffer.getvalue()

    async def _download_image(self, bot, file_id: str):
        from PIL import Image

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
    def _compose_outfit(category_images):
        from PIL import Image

        canvas_width = 1536
        canvas_height = 2304
        canvas = Image.new("RGB", (canvas_width, canvas_height), color=(255, 255, 255))

        slots = {
            "outerwear": (318, 60, 900, 820),
            "top": (318, 140, 900, 760),
            "dress": (278, 120, 980, 1520),
            "bottom": (338, 860, 860, 980),
            "shoes": (378, 1860, 780, 360),
            "accessories": (1090, 150, 320, 320),
        }

        if category_images.get("dress") is not None:
            OutfitImageService._paste_contained(canvas, category_images["dress"], slots["dress"])
        else:
            if category_images.get("outerwear") is not None:
                OutfitImageService._paste_contained(canvas, category_images["outerwear"], slots["outerwear"])
            if category_images.get("top") is not None:
                OutfitImageService._paste_contained(canvas, category_images["top"], slots["top"])
            if category_images.get("bottom") is not None:
                OutfitImageService._paste_contained(canvas, category_images["bottom"], slots["bottom"])

        if category_images.get("shoes") is not None:
            OutfitImageService._paste_contained(canvas, category_images["shoes"], slots["shoes"])

        if category_images.get("accessories") is not None:
            OutfitImageService._paste_contained(canvas, category_images["accessories"], slots["accessories"])

        return canvas

    @staticmethod
    def _paste_contained(canvas, source, box):
        from PIL import Image, ImageOps

        x, y, w, h = box
        fitted = ImageOps.contain(source, (w, h), method=Image.Resampling.LANCZOS)
        paste_x = x + (w - fitted.width) // 2
        paste_y = y + (h - fitted.height) // 2
        canvas.paste(fitted, (paste_x, paste_y))
