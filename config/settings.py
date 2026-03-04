from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    bot_token: str
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
    yookassa_shop_id: str | None = None
    yookassa_secret_key: str | None = None
    yookassa_return_url: str = "https://t.me/wardrobe_24_bot"
    subscription_price: int = 399
    subscription_days: int = 30
    admitad_uid: str = ""
    replicate_api_token: str | None = None


settings = Settings()
