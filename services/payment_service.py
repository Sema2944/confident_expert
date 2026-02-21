"""ЮKassa payment integration."""

import logging
import uuid

from config.settings import settings

logger = logging.getLogger(__name__)

_yookassa_initialized = False


def init_yookassa() -> bool:
    """Инициализация ЮKassa. Возвращает True если настроена."""
    global _yookassa_initialized
    if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
        logger.info("YooKassa credentials not configured, payments disabled")
        return False

    try:
        from yookassa import Configuration
        Configuration.account_id = settings.yookassa_shop_id
        Configuration.secret_key = settings.yookassa_secret_key
        _yookassa_initialized = True
        logger.info("YooKassa initialized successfully")
        return True
    except Exception:
        logger.exception("Failed to initialize YooKassa")
        return False


def is_yookassa_configured() -> bool:
    return _yookassa_initialized


def create_payment(user_id: int, amount: int | None = None) -> dict[str, str] | None:
    """Создать платёж. Возвращает {payment_id, confirmation_url}."""
    if not _yookassa_initialized:
        return None

    price = amount or settings.subscription_price

    try:
        from yookassa import Payment
        payment = Payment.create({
            "amount": {
                "value": f"{price}.00",
                "currency": "RUB",
            },
            "confirmation": {
                "type": "redirect",
                "return_url": settings.yookassa_return_url,
            },
            "capture": True,
            "description": f"Подписка Wardrobe Bot — {settings.subscription_days} дней",
            "metadata": {
                "user_id": str(user_id),
            },
        }, uuid.uuid4())

        return {
            "payment_id": payment.id,
            "confirmation_url": payment.confirmation.confirmation_url,
        }
    except Exception:
        logger.exception("Failed to create payment for user %s", user_id)
        return None


def parse_webhook(body: dict) -> tuple[str, int | None]:
    """Парсит webhook от ЮKassa. Возвращает (event_type, user_id)."""
    try:
        from yookassa.domain.notification import WebhookNotificationEventType, WebhookNotificationFactory
        notification = WebhookNotificationFactory().create(body)
        event_type = notification.event

        user_id = None
        if event_type == WebhookNotificationEventType.PAYMENT_SUCCEEDED:
            metadata = notification.object.metadata or {}
            user_id_str = metadata.get("user_id")
            if user_id_str:
                user_id = int(user_id_str)

        return event_type, user_id
    except Exception:
        logger.exception("Failed to parse YooKassa webhook")
        return "unknown", None
