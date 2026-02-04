from dataclasses import dataclass


@dataclass
class ItemAnalysis:
    type: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    pattern: str | None = None
    season: str | None = None
    formality: str | None = None
    gender_hint: str | None = None


class AIAnalyzeService:
    async def analyze(self, image_bytes: bytes) -> ItemAnalysis:
        # TODO: интеграция с моделью анализа изображения
        return ItemAnalysis(
            type="unknown",
            primary_color="unknown",
            secondary_color="unknown",
            pattern="unknown",
            season="unknown",
            formality="unknown",
            gender_hint="unknown",
        )
