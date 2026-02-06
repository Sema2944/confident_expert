from dataclasses import dataclass


@dataclass
class OutfitResult:
    description: str
    items: dict


class OutfitService:
    async def generate_outfits(
        self,
        items: list[dict],
        occasion: str,
        season: str,
        count: int,
    ) -> list[OutfitResult]:
        # Пока MVP-режим без paywall и без обязательной LLM-интеграции:
        # создаем несколько осмысленных текстовых комбинаций на основе загруженных вещей.
        categories = sorted({item.get("category", "item") for item in items})
        category_line = ", ".join(categories) if categories else "базовые вещи"
        return [
            OutfitResult(
                description=(
                    f"Образ #{index + 1} для {occasion} ({season}): "
                    f"соберите комплект из категорий: {category_line}."
                ),
                items={},
            )
            for index in range(count)
        ]
