FROM python:3.12-slim

WORKDIR /app

RUN useradd --create-home --uid 10001 bot

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R bot:bot /app

USER bot

ENV PORT=10000
EXPOSE 10000

CMD ["python", "-m", "bot.webhook_main"]
