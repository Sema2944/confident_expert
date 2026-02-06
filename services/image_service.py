import base64

import httpx

from config.settings import settings


class ImageService:
    async def generate_image(self, outfit_description: str) -> bytes | None:
        if not settings.image_api_key:
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
        except Exception:
            return None

        data = response.json().get("data") or []
        if not data:
            return None

        b64 = data[0].get("b64_json")
        if b64:
            return base64.b64decode(b64)

        return None
