"""Цены клуба: пробный период, первые 50 участников и обычный месяц.

Продление вручную. Автосписания нет.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import settings


@dataclass(frozen=True)
class PriceQuote:
    kind: str
    amount_rub: int
    days: int


def monthly_quote(
    *,
    has_intro_slot: bool,
    intro_months_used: int,
    confirmed_intro_members: int,
    club_price: int | None = None,
    intro_price: int | None = None,
    intro_months: int | None = None,
    intro_member_limit: int | None = None,
    period_days: int | None = None,
) -> PriceQuote:
    """Цена следующего оплаченного месяца.

    Участник со слотом платит intro_price, пока не израсходованы intro_months.
    Новый участник получает слот, только если подтверждённых слотов меньше лимита.
    """
    club = settings.club_price_rub if club_price is None else club_price
    intro = settings.intro_price_rub if intro_price is None else intro_price
    months = settings.intro_months if intro_months is None else intro_months
    limit = settings.intro_member_limit if intro_member_limit is None else intro_member_limit
    days = settings.club_period_days if period_days is None else period_days

    if has_intro_slot and intro_months_used < months:
        return PriceQuote(kind="intro", amount_rub=intro, days=days)
    if not has_intro_slot and confirmed_intro_members < limit:
        return PriceQuote(kind="intro", amount_rub=intro, days=days)
    return PriceQuote(kind="regular", amount_rub=club, days=days)


def trial_quote(
    *,
    trial_price: int | None = None,
    trial_days: int | None = None,
) -> PriceQuote:
    price = settings.trial_price_rub if trial_price is None else trial_price
    days = settings.trial_days if trial_days is None else trial_days
    return PriceQuote(kind="trial", amount_rub=price, days=days)


def renewal_notice() -> str:
    return "Автосписания нет: когда период закончится, оплатите следующий вручную в боте."


def monthly_price_line(quote: PriceQuote) -> str:
    if quote.kind == "intro":
        return (
            f"Сейчас для вас {quote.amount_rub} ₽ за {quote.days} дней — "
            f"цена первых {settings.intro_member_limit} участников "
            f"на первые {settings.intro_months} месяца. "
            f"Дальше {settings.club_price_rub} ₽ за {settings.club_period_days} дней."
        )
    return f"Стоимость клуба: {quote.amount_rub} ₽ за {quote.days} дней."


def paywall_text(*, quote: PriceQuote, trial_available: bool) -> str:
    lines = [
        "Клуб «Шкаф работает»",
        "Безлимитные образы, показ на манекене, поиск похожих вещей и подбор по погоде.",
        "",
        monthly_price_line(quote),
    ]
    if trial_available:
        lines.append(
            f"Можно начать с {settings.trial_days} дней за {settings.trial_price_rub} ₽."
        )
    lines.append(renewal_notice())
    return "\n".join(lines)


def active_subscription_text(until_label: str, quote: PriceQuote) -> str:
    return (
        f"✅ Клуб активен до {until_label}.\n\n"
        f"Следующий период: {monthly_price_line(quote)}\n"
        f"{renewal_notice()}"
    )
