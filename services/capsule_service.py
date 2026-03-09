"""Capsule wardrobe service — auto-creation and management."""

from __future__ import annotations

import logging

from bot.storage import (
    add_item_to_capsule,
    create_capsule,
    get_capsule_items,
    get_items,
    get_user_capsules,
)

logger = logging.getLogger(__name__)

# Rules for auto-capsule assignment based on item attributes.
_CAPSULE_RULES: dict[str, dict] = {
    "Офис": {
        "icon": "🏢",
        "formality": {"office", "smart"},
    },
    "Кэжуал": {
        "icon": "👕",
        "formality": {"casual"},
    },
    "Вечерний": {
        "icon": "🌙",
        "formality": {"smart"},
        "categories": {"onepiece"},
    },
    "Спорт": {
        "icon": "🏃",
        "formality": {"sport"},
    },
}


def _item_matches_capsule(item: dict, rule: dict) -> bool:
    """Check if an item matches a capsule rule."""
    formality = (item.get("formality") or "").strip().lower()
    category = (item.get("category") or "").strip().lower()

    formality_match = formality in rule.get("formality", set())

    # If rule has categories, item must match category OR formality
    if "categories" in rule:
        return formality_match or category in rule["categories"]

    return formality_match


def suggest_capsules_for_item(item: dict) -> list[str]:
    """Return capsule names that this item could belong to."""
    suggestions = []
    for name, rule in _CAPSULE_RULES.items():
        if _item_matches_capsule(item, rule):
            suggestions.append(name)

    # Neutral basics (black, white, grey, navy, beige) go into all non-sport capsules
    color = (item.get("primary_color") or "").strip().lower()
    _NEUTRAL = {"black", "white", "gray", "grey", "navy", "beige", "brown",
                "чёрный", "белый", "серый", "бежевый", "тёмно-синий", "коричневый"}
    if color in _NEUTRAL and not suggestions:
        # Neutral items without specific formality → suggest Casual + Office
        suggestions = ["Офис", "Кэжуал"]

    return suggestions


async def auto_create_capsules(user_id: int) -> list[dict]:
    """Analyse user wardrobe and create capsules automatically.

    Returns list of created capsules with counts.
    """
    items = await get_items(user_id)
    if not items:
        return []

    existing = await get_user_capsules(user_id)
    existing_names = {c["name"] for c in existing}

    created: list[dict] = []

    for capsule_name, rule in _CAPSULE_RULES.items():
        if capsule_name in existing_names:
            continue

        matching_items = [it for it in items if _item_matches_capsule(it, rule)]
        if len(matching_items) < 2:
            continue

        capsule_id = await create_capsule(user_id, capsule_name, rule["icon"])
        added = 0
        for it in matching_items:
            item_id = it.get("id")
            if item_id and await add_item_to_capsule(capsule_id, item_id):
                added += 1

        created.append({"id": capsule_id, "name": capsule_name, "icon": rule["icon"], "count": added})
        logger.info("Auto-created capsule '%s' for user %s with %d items", capsule_name, user_id, added)

    return created
