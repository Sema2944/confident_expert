# Переезд бота с Render на свой сервер

Бот — Telegram `@wardrobe_24_bot` и MAX. Сейчас он работает на Render. Здесь — как поставить его на ваш VPS (Ubuntu 22.04, `72.56.241.204`), не трогая чужие сайты и чужие базы.

На сервере стоит старый `docker-compose` 1.29.2. Команды ниже с дефисом. Если позже появится плагин v2, те же команды пишутся через пробел: `docker compose`.

Ничего само не выкладывается. Пока идёт фаза А, бот на Render продолжает отвечать людям.

## Что получится

- Свой Postgres в контейнере `shkaf-postgres`. Наружу порт базы не открывается. Чужие Postgres на портах 5433 и 5434 не используются.
- Контейнер бота `shkaf-bot`. С хоста он доступен только как `127.0.0.1:8095`. Порт 10000 на сервере уже занят, его не трогаем.
- Telegram на VPS — long polling. Отдельный вебхук Telegram не нужен.
- nginx с HTTPS принимает `https://bot.shkaf-rabotaet.ru` и отдаёт его на `127.0.0.1:8095`. Оплата ЮKassa: `https://bot.shkaf-rabotaet.ru/yookassa/webhook`.

Пока переменная `TG_MODE` не задана, бот как на Render: режим `webhook`.

## Фаза А. Подготовка, Render ещё работает

### А1. Секреты с Render

В панели Render откройте переменные сервиса и перепишите их в менеджер паролей. Не в чат и не в git.

Нужны как минимум: `BOT_TOKEN`, `MAX_BOT_TOKEN` (если MAX включён), `AI_API_KEY`, `IMAGE_API_KEY`, `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`, `YOOKASSA_RETURN_URL`, `ADMIN_ID`, `WEBHOOK_SECRET` если был, ключи S3 и Admitad если пользовались.

Запишите текущий URL уведомлений ЮKassa — он нужен для отката.

Если на Render был свой Postgres (`DB_URL`), сделайте `pg_dump` и сохраните файл. Скрипт из SQLite тогда не нужен. Если `DB_URL` не было, живых данных на диске Render обычно нет: диск стирается при перезапуске. Скрипт ниже — на случай, если файл `wardrobe.sqlite3` всё же сохранился.

### А2. DNS

У регистратора:

- имя: `bot.shkaf-rabotaet.ru`
- тип: `A`
- значение: `72.56.241.204`

Проверка: `dig +short bot.shkaf-rabotaet.ru` показывает этот адрес.

### А3. Каталог и .env

```bash
sudo mkdir -p /opt/wardrobe-bot
sudo chown "$USER" /opt/wardrobe-bot
cd /opt/wardrobe-bot
git clone https://github.com/Sema2944/confident_expert.git .
git checkout main
cp .env.example .env
chmod 600 .env
```

В `.env` вставьте секреты с Render и эти строки:

```env
COMPOSE_PROJECT_NAME=shkaf
TG_MODE=polling
HOST_PORT=8095
PORT=10000
POSTGRES_USER=wardrobe
POSTGRES_PASSWORD=придумайте_длинный_пароль
POSTGRES_DB=wardrobe
```

`PORT=10000` — порт внутри контейнера. Снаружи nginx ходит на `HOST_PORT` (8095). `DB_URL` можно не писать: compose подставляет адрес `postgres` внутри своей сети. В пароле Postgres не используйте `@`, `:`, `/` и `#`.

`REDIS_URL` оставьте пустым. `YOOKASSA_IP_CHECK=true` можно оставить.

Файл `.env` не коммитьте.

### А4. Сборка и только база

Образ собирается, контейнер бота не стартует. Render в это время ещё работает.

```bash
cd /opt/wardrobe-bot
docker-compose -p shkaf build
docker-compose -p shkaf up -d postgres
docker-compose -p shkaf ps
```

В списке должен быть `shkaf-postgres` и не должно быть запущенного `shkaf-bot`. Портов вида `0.0.0.0:5432` у этого контейнера нет.

Если сохранился SQLite, положите его рядом и откройте чтение: `chmod a+r wardrobe.sqlite3`. Одноразовый контейнер только копирует данные и завершается, Telegram он не слушает:

```bash
docker-compose -p shkaf run --rm \
  -v "$PWD/wardrobe.sqlite3:/data/wardrobe.sqlite3:ro" \
  bot python scripts/sqlite_to_postgres.py /data/wardrobe.sqlite3
```

Повторный запуск пишет `новых строк 0`. Если живая база была Postgres на Render, залейте дамп в `shkaf-postgres`, а не этот скрипт.

### А5. nginx, только этот домен

Чужие сайты не редактируем. Сначала копия всей конфигурации:

```bash
sudo tar -C / -czf "$HOME/nginx-backup-before-shkaf.tar.gz" etc/nginx
```

Новый файл и больше ничего. Сохраните как `/etc/nginx/sites-available/shkaf-bot`:

```bash
sudo tee /etc/nginx/sites-available/shkaf-bot >/dev/null <<'EOF'
server {
    listen 80;
    server_name bot.shkaf-rabotaet.ru;

    location / {
        proxy_pass http://127.0.0.1:8095;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
sudo ln -s /etc/nginx/sites-available/shkaf-bot /etc/nginx/sites-enabled/shkaf-bot
sudo nginx -t
```

Если `nginx -t` пишет ошибку, симлинк сразу уберите и не делайте reload:

```bash
sudo rm -f /etc/nginx/sites-enabled/shkaf-bot
sudo nginx -t
```

Если проверка прошла:

```bash
sudo systemctl reload nginx
sudo certbot --nginx -d bot.shkaf-rabotaet.ru
```

Только этот домен. Не запускайте `certbot` без `-d`: он может задеть чужие сайты.

Пока бот не запущен, `curl -sS https://bot.shkaf-rabotaet.ru/` может вернуть 502. Так и должно быть в фазе А. Сертификат при этом уже выдан.

## Фаза Б. Переключение, несколько минут

Два процесса сразу не держите: и Render, и VPS начнут отвечать на одни и те же сообщения.

1. В Render нажмите Suspend у сервиса бота и дождитесь, что он не Live.
2. На сервере:

```bash
cd /opt/wardrobe-bot
docker-compose -p shkaf up -d bot
docker-compose -p shkaf logs -f bot
```

В логах:

- `Storage backend: PostgreSQL host=postgres port=5432 dbname=wardrobe user=wardrobe` — без пароля
- `Telegram mode: polling`
- `HTTP server started on 0.0.0.0:10000` — это порт внутри контейнера
- `Telegram getMe: id=... username=@wardrobe_24_bot`

Ctrl+C только закрывает просмотр логов.

3. Проверка:

```bash
curl -sS http://127.0.0.1:8095/
curl -sS https://bot.shkaf-rabotaet.ru/
```

Оба ответа: `OK`. Напишите боту в Telegram. Ответ должен прийти один раз.

4. В кабинете ЮKassa смените URL уведомлений на `https://bot.shkaf-rabotaet.ru/yookassa/webhook`, событие `payment.succeeded`. Автоплатежи не включайте.

Если в логах `YooKassa webhook rejected`, в `.env` поставьте `YOOKASSA_IP_CHECK=false` и выполните `docker-compose -p shkaf up -d bot`. Платёж всё равно сверяется с API ЮKassa.

## Фаза В. Откат

1. Остановить только бота на VPS. Базу можно оставить, она наружу не торчит:

```bash
cd /opt/wardrobe-bot
docker-compose -p shkaf stop bot
```

2. В ЮKassa верните прежний URL Render.
3. В Render нажмите Resume. При старте бот снова поставит Telegram-вебхук.
4. Напишите боту и убедитесь, что ответ один.

Убрать сайт nginx, если он больше не нужен. Сначала проверка, потом reload:

```bash
sudo rm -f /etc/nginx/sites-enabled/shkaf-bot
sudo nginx -t && sudo systemctl reload nginx
sudo certbot delete --cert-name bot.shkaf-rabotaet.ru
```

Если `nginx -t` после любых правок ругается, верните копию и не оставляйте сломанный nginx:

```bash
sudo tar -C / -xzf "$HOME/nginx-backup-before-shkaf.tar.gz"
sudo nginx -t && sudo systemctl reload nginx
```

Чужие файлы в `sites-enabled` этим откатом сайта бота не удаляются. Полный tar нужен только если сломался весь nginx.

## Переменные

| Переменная | Зачем |
| --- | --- |
| `BOT_TOKEN` | Telegram |
| `TG_MODE=polling` | long polling; compose ставит это сам |
| `COMPOSE_PROJECT_NAME=shkaf` | имя проекта compose, чтобы не смешаться с чужими контейнерами |
| `HOST_PORT=8095` | порт на localhost сервера |
| `PORT=10000` | порт процесса внутри контейнера |
| `POSTGRES_PASSWORD` | пароль базы, только внутри сети compose |
| `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` | оплата |
| `AI_API_KEY` | разбор фото |

`REDIS_URL` не обязателен. Пустые `DB_URL` и `DATABASE_URL` в `.env` на VPS нормальны: адрес базы задаёт compose.
