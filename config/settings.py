from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    db_url: str
    payment_provider_token: str | None = None
    ai_api_key: str | None = None
    ai_api_base: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4.1-mini"
    image_api_key: str | None = None
    image_api_base: str = "https://api.openai.com/v1"
    image_model: str = "gpt-image-1"
    image_size: str = "1024x1792"
    stt_api_key: str | None = None
    fashion_trend_feeds: str | None = None
    max_items_per_user: int = 60
    rate_limit_upload_per_min: int = 10
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
