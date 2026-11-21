"""Свободный текст вне анкет: образ, повод или короткая подсказка."""

from __future__ import annotations

import re

_OCCASION_HINTS: tuple[tuple[str, str], ...] = (
    ("work_office", ("работ", "офис")),
    ("interview", ("собесед",)),
    ("date", ("свидан",)),
    ("party", ("вечерин",)),
    ("walk", ("прогул",)),
    ("sport_active", ("спорт",)),
)

_OUTFIT_HINTS = ("образ", "собери", "собрат", "собир", "подбер")


def _normalize(text: str) -> str:
    lowered = (text or "").lower().replace("ё", "е")
    cleaned = re.sub(r"[^\w\s/]+", " ", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", cleaned).strip()


def interpret_free_text(text: str) -> str | None:
    """'outfit', код повода или None.

    Повод важнее общей просьбы собрать образ: «собери образ на работу» — это офис.
    """
    normalized = _normalize(text)
    if not normalized:
        return None
    for code, hints in _OCCASION_HINTS:
        if any(hint in normalized for hint in hints):
            return code
    if any(hint in normalized for hint in _OUTFIT_HINTS):
        return "outfit"
    return None
