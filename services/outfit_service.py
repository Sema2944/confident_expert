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
        # TODO: интеграция с LLM
        return [
            OutfitResult(
                description=f"Образ #{index + 1} для {occasion} ({season}).",
                items={},
            )
            for index in range(count)
        ]
