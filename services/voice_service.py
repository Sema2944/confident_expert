from dataclasses import dataclass


@dataclass
class VoiceIntent:
    occasion: str | None = None
    season: str | None = None


class VoiceService:
    async def extract_intent(self, audio_bytes: bytes) -> VoiceIntent:
        # TODO: интеграция со STT
        return VoiceIntent()
