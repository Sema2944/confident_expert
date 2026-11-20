"""ЮKassa: разовый платёж и проверка вебхука.

Автосписания нет: карта не сохраняется, следующий период пользователь оплачивает сам.
Вебхук не активирует клуб по телу запроса. Платёж заново читается из API ЮKassa,
сумма и user_id сверяются с локальной записью, повторный payment_id игнорируется.
"""

from __future__ import annotations

import ipaddress
import logging
import uuid
from decimal import Decimal, InvalidOperation

from config.settings import settings

logger = logging.getLogger(__name__)

_yookassa_initialized = False

# https://yookassa.ru/developers/using-api/webhooks
_YOOKASSA_NETWORKS = (
    ipaddress.ip_network("185.71.76.0/27"),
    ipaddress.ip_network("185.71.77.0/27"),
    ipaddress.ip_network("77.75.153.0/25"),
    ipaddress.ip_network("77.75.154.128/25"),
    ipaddress.ip_network("77.75.156.11/32"),
    ipaddress.ip_network("77.75.156.35/32"),
    ipaddress.ip_network("2a02:5180::/32"),
)


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


def yookassa_ip_allowed(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    return any(address in network for network in _YOOKASSA_NETWORKS)


def client_ip_from_headers(forwarded_for: str | None, remote: str | None) -> str | None:
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    if remote:
        return str(remote).strip() or None
    return None


def create_payment(
    user_id: int,
    amount: int | None = None,
    *,
    amount_rub: int | None = None,
    kind: str = "regular",
    days: int | None = None,
) -> dict[str, str] | None:
    """Создать разовый платёж. Возвращает {payment_id, confirmation_url} или None.

    Функция синхронная: SDK ЮKassa не async. Её нельзя await-ить.
    """
    if not _yookassa_initialized:
        return None

    price = amount_rub if amount_rub is not None else amount
    if price is None:
        price = settings.club_price_rub
    period = days if days is not None else settings.club_period_days
    if kind == "trial":
        description = f"Пробный доступ «Шкаф работает» — {period} дн."
    else:
        description = f"Клуб «Шкаф работает» — {period} дн."

    try:
        from yookassa import Payment
        payment = Payment.create({
            "amount": {
                "value": f"{int(price)}.00",
                "currency": "RUB",
            },
            "confirmation": {
                "type": "redirect",
                "return_url": settings.yookassa_return_url,
            },
            "capture": True,
            "description": description,
            "metadata": {
                "user_id": str(user_id),
                "kind": kind,
                "days": str(period),
            },
        }, uuid.uuid4())

        return {
            "payment_id": payment.id,
            "confirmation_url": payment.confirmation.confirmation_url,
        }
    except Exception:
        logger.exception("Failed to create payment for user %s", user_id)
        return None


async def start_checkout(user_id: int, kind: str) -> dict[str, str] | None:
    """Считает цену, создаёт платёж в ЮKassa и сохраняет его id до вебхука."""
    from bot.storage import get_club_state, save_payment_intent
    from services.pricing import trial_quote
    from services.subscription_service import quote_monthly_for_user

    if kind == "trial":
        state = await get_club_state(user_id)
        if int(state.get("trial_paid") or 0) or int(state.get("club_paid") or 0):
            return None
        quote = trial_quote()
    elif kind == "monthly":
        quote = await quote_monthly_for_user(user_id)
    else:
        return None

    result = create_payment(
        user_id,
        amount_rub=quote.amount_rub,
        kind=quote.kind,
        days=quote.days,
    )
    if not result:
        return None
    await save_payment_intent(
        payment_id=result["payment_id"],
        user_id=user_id,
        amount_rub=quote.amount_rub,
        kind=quote.kind,
        days=quote.days,
    )
    return result


def fetch_yookassa_payment(payment_id: str) -> dict:
    """Читает платёж из API ЮKassa. Телу вебхука не доверяем."""
    from yookassa import Payment
    payment = Payment.find_one(payment_id)
    amount = payment.amount
    metadata = getattr(payment, "metadata", None)
    user_id = ""
    if isinstance(metadata, dict):
        user_id = str(metadata.get("user_id") or "")
    elif metadata is not None:
        user_id = str(getattr(metadata, "user_id", "") or "")
        if not user_id and hasattr(metadata, "get"):
            user_id = str(metadata.get("user_id") or "")
    return {
        "id": str(payment.id),
        "status": str(payment.status),
        "amount": str(amount.value),
        "currency": str(amount.currency),
        "user_id": user_id,
    }


def amounts_match(remote_amount: str, expected_rub: int) -> bool:
    try:
        return Decimal(str(remote_amount)) == Decimal(int(expected_rub))
    except (InvalidOperation, ValueError):
        return False


def payment_matches_intent(intent: dict, remote: dict) -> str | None:
    """None если платёж из API совпал с локальной записью, иначе причина отказа."""
    if str(remote.get("status") or "") != "succeeded":
        return "status"
    if str(remote.get("currency") or "").upper() != "RUB":
        return "currency"
    if str(remote.get("id") or "") != str(intent.get("payment_id") or ""):
        return "id"
    if not amounts_match(str(remote.get("amount") or ""), int(intent["amount_rub"])):
        return "amount"
    if str(remote.get("user_id") or "") != str(intent.get("user_id") or ""):
        return "user"
    return None


def extract_webhook_payment(body: dict) -> tuple[str, str | None]:
    event = str(body.get("event") or "")
    obj = body.get("object") or {}
    payment_id = obj.get("id")
    return event, str(payment_id) if payment_id else None


async def handle_yookassa_notification(
    *,
    body: dict,
    source_ip: str | None,
    fetch_payment=fetch_yookassa_payment,
) -> dict:
    """Возвращает {status, activated, user_id, days, reason}.

    activated=True только когда клуб продлён этим вызовом.
    """
    from bot.storage import get_payment_record
    from services.subscription_service import apply_payment_once

    if settings.yookassa_ip_check and not (source_ip and yookassa_ip_allowed(source_ip)):
        logger.warning("YooKassa webhook rejected for ip=%s", source_ip)
        return {"status": 403, "activated": False, "user_id": None, "days": None, "reason": "ip"}

    event, payment_id = extract_webhook_payment(body)
    if not payment_id:
        return {"status": 400, "activated": False, "user_id": None, "days": None, "reason": "no_id"}
    if event != "payment.succeeded":
        return {"status": 200, "activated": False, "user_id": None, "days": None, "reason": "ignored"}

    try:
        remote = fetch_payment(payment_id)
    except Exception:
        logger.exception("Failed to re-fetch YooKassa payment %s", payment_id)
        return {"status": 502, "activated": False, "user_id": None, "days": None, "reason": "fetch"}

    intent = await get_payment_record(payment_id)
    if not intent:
        logger.warning("YooKassa payment %s has no local intent", payment_id)
        return {"status": 400, "activated": False, "user_id": None, "days": None, "reason": "unknown"}
    if intent["status"] == "succeeded":
        return {
            "status": 200,
            "activated": False,
            "user_id": int(intent["user_id"]),
            "days": int(intent["days"]),
            "reason": "duplicate",
        }

    mismatch = payment_matches_intent(intent, remote)
    if mismatch:
        logger.warning("YooKassa payment %s rejected: %s", payment_id, mismatch)
        return {"status": 400, "activated": False, "user_id": None, "days": None, "reason": mismatch}

    claimed = await apply_payment_once(payment_id)
    if not claimed:
        return {
            "status": 200,
            "activated": False,
            "user_id": int(intent["user_id"]),
            "days": int(intent["days"]),
            "reason": "duplicate",
        }
    logger.info(
        "YooKassa payment %s activated user %s kind=%s days=%s",
        payment_id,
        claimed["user_id"],
        claimed["kind"],
        claimed["days"],
    )
    return {
        "status": 200,
        "activated": True,
        "user_id": int(claimed["user_id"]),
        "days": int(claimed["days"]),
        "reason": "activated",
    }


def parse_webhook(body: dict) -> tuple[str, int | None]:
    """Старый разбор тела. Для активации не используется."""
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
