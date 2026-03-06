import logging
from io import BytesIO
from PIL import Image
import boto3
from botocore.config import Config
from config.settings import settings

logger = logging.getLogger(__name__)


class S3StorageService:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None and settings.s3_access_key:
            self._client = boto3.client(
                's3',
                endpoint_url=settings.s3_endpoint,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                config=Config(signature_version='s3v4'),
            )
        return self._client

    @property
    def enabled(self) -> bool:
        return bool(settings.s3_access_key and settings.s3_secret_key)

    def _key(self, user_id: int, item_id: int) -> str:
        return f"photos/{user_id}/{item_id}.jpg"

    def _compress_photo(self, photo_bytes: bytes, max_size: int = 800) -> bytes:
        """Сжимает фото до max_size×max_size, качество 85%"""
        img = Image.open(BytesIO(photo_bytes))
        img = img.convert("RGB")
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue()

    def upload_photo(self, user_id: int, item_id: int, photo_bytes: bytes) -> str | None:
        """Сжимает и загружает фото. Возвращает URL или None."""
        if not self.enabled:
            return None
        try:
            compressed = self._compress_photo(photo_bytes)
            key = self._key(user_id, item_id)
            self.client.put_object(
                Bucket=settings.s3_bucket,
                Key=key,
                Body=compressed,
                ContentType='image/jpeg',
            )
            url = f"{settings.s3_endpoint}/{settings.s3_bucket}/{key}"
            logger.info("Uploaded photo to S3: %s (%d bytes)", key, len(compressed))
            return url
        except Exception:
            logger.exception("Failed to upload photo to S3")
            return None

    def get_photo(self, user_id: int, item_id: int) -> bytes | None:
        """Скачивает фото из S3."""
        if not self.enabled:
            return None
        try:
            key = self._key(user_id, item_id)
            response = self.client.get_object(Bucket=settings.s3_bucket, Key=key)
            return response['Body'].read()
        except Exception:
            logger.exception("Failed to get photo from S3")
            return None

    def delete_photo(self, user_id: int, item_id: int) -> bool:
        if not self.enabled:
            return False
        try:
            key = self._key(user_id, item_id)
            self.client.delete_object(Bucket=settings.s3_bucket, Key=key)
            return True
        except Exception:
            logger.exception("Failed to delete photo from S3")
            return False


s3_service = S3StorageService()
