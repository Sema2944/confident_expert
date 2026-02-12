import base64
import logging

import httpx

from config.settings import settings


class ImageService:
    async def generate_image(self, outfit_description: str) -> bytes | None:
        if not settings.image_api_key:
            logging.warning("IMAGE_API_KEY is empty; image generation is disabled.")
            return None

        headers = {
            "Authorization": f"Bearer {settings.image_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.image_model,
            "prompt": outfit_description,
            "size": "1024x1024",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{settings.image_api_base.rstrip('/')}/images/generations",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except Exception as error:
            logging.exception("Image generation request failed: %s", error)
            return None

        data = response.json().get("data") or []
        if not data:
            logging.warning("Image API returned empty data array.")
            return None

        b64 = data[0].get("b64_json")
        if b64:
            return base64.b64decode(b64)

        image_url = data[0].get("url")
        if image_url:
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    image_response = await client.get(image_url)
                    image_response.raise_for_status()
                return image_response.content
            except Exception as error:
                logging.exception("Failed to download generated image by URL: %s", error)
                return None

        logging.warning("Image API response has neither b64_json nor url.")
        return None
