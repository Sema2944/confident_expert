import asyncio
import base64
import logging

import httpx

from config.settings import settings


class ImageService:
    _MAX_RETRIES = 3

    async def generate_image(self, outfit_description: str) -> bytes | None:
        if not settings.image_api_key:
            logging.warning("IMAGE_API_KEY is empty; image generation is disabled.")
            return None

        requested_size = settings.image_size
        image_bytes = await self._request_image(prompt=outfit_description, size=requested_size)
        if image_bytes is not None:
            return image_bytes

        if requested_size != "1024x1024":
            logging.info("Retrying image generation with fallback size 1024x1024.")
            return await self._request_image(prompt=outfit_description, size="1024x1024")

        return None

    async def _request_image(self, prompt: str, size: str) -> bytes | None:
        headers = {
            "Authorization": f"Bearer {settings.image_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.image_model,
            "prompt": prompt,
            "size": size,
        }

        response = None
        for attempt in range(self._MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{settings.image_api_base.rstrip('/')}/images/generations",
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                break
            except httpx.HTTPStatusError as error:
                if self._is_unsupported_size_error(error):
                    logging.warning("Image API does not support size %s for model %s.", size, settings.image_model)
                    return None
                if error.response.status_code == 429 and attempt < self._MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    logging.warning("Image API rate limited (429), retrying in %d sec (attempt %d/%d)", wait, attempt + 1, self._MAX_RETRIES)
                    await asyncio.sleep(wait)
                    continue
                logging.exception("Image generation request failed: %s", error)
                return None
            except Exception as error:
                logging.exception("Image generation request failed: %s", error)
                return None
        else:
            logging.error("Image generation failed after %d retries (rate limited)", self._MAX_RETRIES)
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

    @staticmethod
    def _is_unsupported_size_error(error: httpx.HTTPStatusError) -> bool:
        response_text = (error.response.text or "").lower()
        return "size" in response_text and "unsupported" in response_text
