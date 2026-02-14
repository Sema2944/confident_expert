from __future__ import annotations

from io import BytesIO

from aiogram import Bot
from PIL import Image, ImageOps


class OutfitImageService:
    _CATEGORY_ORDER = ["top", "bottom", "dress", "outerwear", "shoes", "accessories"]

    async def render_outfit_image(self, bot: Bot, items_payload: dict[str, list[str]]) -> bytes | None:
        file_ids: list[str] = []
        for category in self._CATEGORY_ORDER:
            file_ids.extend(items_payload.get(category, []))

        if not file_ids:
            return None

        images: list[Image.Image] = []
        for file_id in file_ids:
            image = await self._download_image(bot=bot, file_id=file_id)
            if image is not None:
                images.append(image)

        if not images:
            return None

        composed = self._compose_vertical(images)
        buffer = BytesIO()
        composed.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()

    async def _download_image(self, bot: Bot, file_id: str) -> Image.Image | None:
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
    def _compose_vertical(images: list[Image.Image]) -> Image.Image:
        target_width = 1024
        panel_height = 360
        spacing = 24
        margin = 24

        total_height = margin * 2 + len(images) * panel_height + (len(images) - 1) * spacing
        canvas = Image.new("RGB", (target_width, total_height), color=(245, 245, 245))

        y = margin
        for source in images:
            fitted = ImageOps.fit(source, (target_width - margin * 2, panel_height), method=Image.Resampling.LANCZOS)
            canvas.paste(fitted, (margin, y))
            y += panel_height + spacing

        return canvas
