diff --git a/README.md b/README.md
index e1f2dac77a41a68d94e91c81d79d7abc608f8bdf..af79e41d921e3919ebd5d939e34f43449b896546 100644
--- a/README.md
+++ b/README.md
@@ -10,34 +10,42 @@ MVP scaffold for the wardrobe → outfits bot described in the technical specifi
 
 ## Project Structure
 ```
 api/                # Optional FastAPI webhook/admin
 bot/                # Aiogram handlers + FSM
 config/             # Settings and logging
 db/                 # SQLAlchemy models and session
 prompts/            # LLM prompts
 services/           # Business logic
 workers/            # Background tasks (optional)
 ```
 
 ## Setup
 1. Create and activate a virtualenv
 2. Install dependencies
 
 ```
 pip install -r requirements.txt
 ```
 
 3. Copy env and fill values
 ```
 cp .env.example .env
 ```
 
+4. Configure image generation (otherwise the bot will answer without pictures)
+```
+IMAGE_API_KEY=<your_api_key>
+IMAGE_API_BASE=https://api.openai.com/v1
+IMAGE_MODEL=gpt-image-1
+```
+
+
 ## Run (long polling)
 ```
 python -m bot.main
 ```
 
 ## Notes
 - Replace the prompt files in `prompts/` with the approved production versions.
 - Use a proper task queue (RQ/Celery) for image generation in production.
 
