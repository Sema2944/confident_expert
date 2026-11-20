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

## Club

Access is a paid club, not three free outfits. Defaults: 990 ₽ for 30 days,
a 3-day trial for 1 ₽, and 690 ₽ per 30 days for the first 50 paying members
for their first 3 months. Renewal is manual: the bot does not save a card and
does not charge again by itself. Prices are `CLUB_PRICE_RUB`, `CLUB_PERIOD_DAYS`,
`TRIAL_PRICE_RUB`, `TRIAL_DAYS`, `INTRO_PRICE_RUB`, `INTRO_MEMBER_LIMIT`, and
`INTRO_MONTHS`. `YOOKASSA_IP_CHECK=true` rejects a payment webhook whose client
IP is outside YooKassa's published ranges. Activation still re-fetches the
payment from the YooKassa API and ignores a repeated `payment_id`.

## Schedulers

`CHANNEL_AUTOPOST_ENABLED` (default `false`) only seeds and publishes posts to the
Telegram channel `@shkaf_rabotaet`. It does not control messages to users.
Leave it off on Render: the SQLite file does not survive restarts. Posts that were
already sent are not reset to pending. Unsent posts older than 30 minutes are
stored as expired and are not published on startup.

`USER_SCHEDULER_ENABLED` (default `true`) sends morning outfits, paywall follow-ups,
and the 21:00 admin report. Each delivery is claimed in `user_scheduler_claims`
before it is sent, so a restart does not send that same morning outfit, follow-up,
or daily report again while the database is still there. On Render the SQLite file
is wiped together with those claims and with the user rows, so a fresh process has
nobody left to message.

## Notes
- Replace the prompt files in `prompts/` with the approved production versions.
- Use a proper task queue (RQ/Celery) for image generation in production.
- For pilot testing and feedback collection, use the built-in feedback flow and periodically export SQLite data.
