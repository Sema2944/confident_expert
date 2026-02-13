diff --git a/config/settings.py b/config/settings.py
index fff2a71dd2f696e145df895898e3e9bd488922b1..07f27dde787a553bf76293dac45c9a22cf3c90fe 100644
--- a/config/settings.py
+++ b/config/settings.py
@@ -1,20 +1,23 @@
-from pydantic_settings import BaseSettings
+from pydantic_settings import BaseSettings, SettingsConfigDict
 
 
 class Settings(BaseSettings):
     bot_token: str
     db_url: str
     payment_provider_token: str | None = None
     ai_api_key: str | None = None
     image_api_key: str | None = None
+    image_api_base: str = "https://api.openai.com/v1"
+    image_model: str = "gpt-image-1"
     stt_api_key: str | None = None
     max_items_per_user: int = 60
     rate_limit_upload_per_min: int = 10
     log_level: str = "INFO"
 
-    class Config:
-        env_file = ".env"
-        case_sensitive = False
+    model_config = SettingsConfigDict(
+        env_file=".env",
+        case_sensitive=False,
+    )
 
 
 settings = Settings()
