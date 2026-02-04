# Telegram Wardrobe Bot (MVP)

MVP scaffold for the wardrobe → outfits bot described in the technical specification.

## Features (MVP)
- Wardrobe upload and browsing
- Outfit requests by occasion and season
- Trial gating + subscription access
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

## Run (long polling)
```
python -m bot.main
```

## Notes
- Replace the prompt files in `prompts/` with the approved production versions.
- Use a proper task queue (RQ/Celery) for image generation in production.

