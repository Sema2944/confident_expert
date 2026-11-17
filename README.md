# Telegram Wardrobe Bot (MVP)

MVP scaffold for the wardrobe → outfits bot described in the technical specification.

## Features (MVP)
- Wardrobe upload and browsing
- Outfit requests by occasion and season
- Trial gating + subscription access
- Optional voice intent extraction
- Template-based photo processing tool (combine user photos into a fixed output format)
- Feedback collection from users (`/feedback` and `📝 Обратная связь`)
- Multi-user persistent wardrobe storage (SQLite)

## Project Structure
api/ # Optional FastAPI webhook/admin
bot/ # Aiogram handlers + FSM
config/ # Settings and logging
db/ # SQLAlchemy models and session
prompts/ # LLM prompts
services/ # Business logic
workers/ # Background tasks (optional)


## Setup
1. Create and activate a virtualenv
2. Install dependencies

pip install -r requirements.txt

3. Copy env and fill values
cp .env.example .env

4. Configure item analysis (otherwise uploaded items will have unknown attributes)
AI_API_KEY=<your_api_key>
AI_API_BASE=https://api.openai.com/v1
AI_MODEL=gpt-4.1-mini

5. Configure image generation (otherwise the bot will answer without pictures)
IMAGE_API_KEY=<your_api_key>
IMAGE_API_BASE=https://api.openai.com/v1
IMAGE_MODEL=gpt-image-1

6. (Optional) configure path for persistent local storage used by wardrobe and feedback:
WARDROBE_STORAGE_PATH=./data/wardrobe.sqlite3

## Run (long polling)
python -m bot.main

## Channel autopost

Posts to the Telegram channel run only when `CHANNEL_AUTOPOST_ENABLED=true`.
The default is `false`: startup does not seed `scheduled_posts` and does not start
`scheduler_loop`. That loop also sends morning outfits, paywall follow-ups, and the
21:00 admin report, so those stay off while the flag is false.
Leave the flag off unless storage survives restarts (PostgreSQL via `DB_URL`).
The SQLite file (`WARDROBE_STORAGE_PATH`) is local and is lost on Render, which has
no persistent disk. Posts that are already sent are never reset to pending. Unsent
posts older than 30 minutes are stored as expired and are not published on startup.

## Notes
- Replace the prompt files in `prompts/` with the approved production versions.
- Use a proper task queue (RQ/Celery) for image generation in production.
- For pilot testing and feedback collection, use the built-in feedback flow and periodically export SQLite data.
