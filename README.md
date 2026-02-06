# Telegram Wardrobe Bot (MVP)

MVP scaffold for the wardrobe → outfits bot described in the technical specification.

## Features (MVP)
- Wardrobe upload and browsing
- Outfit requests by occasion and season
- Test mode without trial/paywall restrictions
- Optional voice intent extraction

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

4. Set required values in `.env` (minimum is `BOT_TOKEN`)

Example:
```
BOT_TOKEN=123456:ABCDEF
DB_URL=sqlite+aiosqlite:///./wardrobe.db
IMAGE_API_KEY=...
IMAGE_API_BASE=https://api.openai.com/v1
IMAGE_MODEL=gpt-image-1
```

## Run (long polling)
```
python -m bot.main
```

If you see `TelegramConflictError: terminated by other getUpdates request`, it means more than one bot instance is running with the same token. Stop other bot processes (local machine/old Render service) and redeploy only one instance.

## Notes
- Replace the prompt files in `prompts/` with the approved production versions.
- Use a proper task queue (RQ/Celery) for image generation in production.
