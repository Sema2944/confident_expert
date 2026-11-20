# Переезд бота с Render на свой сервер

Бот — Telegram `@wardrobe_24_bot` и MAX. Сейчас он на Render. Этот файл — как запустить его на вашем VPS (Ubuntu, адрес `72.56.241.204`), не мешая проектам, которые там уже работают.

Ничего само не выкладывается. Команды ниже запускаете вы, когда будете готовы.

## Что получится

- База — Postgres в Docker, данные лежат в томе и не пропадают при перезапуске.
- Telegram — long polling (`TG_MODE=polling`), отдельный адрес вебхука Telegram не нужен.
- На сервере всё равно слушает порт `10000` (только с самого сервера): проверка живости `/` и оплата `POST /yookassa/webhook`. Снаружи его открывает nginx с HTTPS.
- MAX, если задан `MAX_BOT_TOKEN`, стартует вместе с процессом, как раньше.

Пока `TG_MODE` не задан, бот ведёт себя как на Render: режим `webhook`.

## 1. Что скопировать с Render заранее

В панели Render откройте сервис бота и переменные окружения. Перепишите их себе в надёжное место (менеджер паролей), не в чат и не в git.

Нужны как минимум:

- `BOT_TOKEN`
- `MAX_BOT_TOKEN` (если MAX включён)
- `AI_API_KEY`, `IMAGE_API_KEY` и остальные ключи, которые у вас заполнены
- `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`
- `YOOKASSA_RETURN_URL` (сейчас `https://t.me/wardrobe_24_bot`)
- `ADMIN_ID`
- `WEBHOOK_SECRET`, если он был
- ключи S3 и Admitad, если пользовались

Если на Render был `DB_URL` с Postgres — сделайте дамп этой базы (`pg_dump`) и сохраните файл. Тогда скрипт из SQLite не нужен: данные уже в Postgres, их можно залить в новый контейнер через `pg_restore` / `psql`.

Если `DB_URL` не было, бот хранил SQLite на диске Render. Этот диск стирается при перезапуске, живых данных там обычно нет. Скрипт переноса всё равно есть на случай, если файл `wardrobe.sqlite3` у вас сохранился.

Запишите текущий адрес вебхука ЮKassa (старый URL на Render). Он понадобится, если придётся откатиться.

## 2. Подготовить сервер

Зайдите на сервер как обычно. Docker и nginx, скорее всего, уже стоят. Проверьте:

```bash
docker --version
docker compose version
nginx -v
```

Если чего-то нет:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 nginx certbot python3-certbot-nginx
sudo systemctl enable --now docker nginx
```

Порт `10000` на localhost не должен быть занят другим проектом:

```bash
ss -ltnp | grep 10000 || echo "порт 10000 свободен"
```

Если занят — в `docker-compose.yml` замените левую часть `127.0.0.1:10000:10000` на свободный порт и тот же порт укажите в nginx ниже.

## 3. DNS

У регистратора домена создайте запись:

- имя: `bot.shkaf-rabotaet.ru`
- тип: `A`
- значение: `72.56.241.204`

Подождите, пока имя начнёт открываться на этот адрес (`dig +short bot.shkaf-rabotaet.ru`).

## 4. Код и файл .env

На сервере, в отдельной папке, не внутри чужих проектов:

```bash
sudo mkdir -p /opt/wardrobe-bot
sudo chown "$USER" /opt/wardrobe-bot
cd /opt/wardrobe-bot
git clone https://github.com/Sema2944/confident_expert.git .
git checkout main
cp .env.example .env
chmod 600 .env
```

Откройте `.env` и вставьте значения с Render. Секреты оставьте пустыми только там, где ключа у вас нет.

Для этого сервера обязательно:

```env
TG_MODE=polling
PORT=10000
POSTGRES_USER=wardrobe
POSTGRES_PASSWORD=придумайте_длинный_пароль
POSTGRES_DB=wardrobe
```

`DB_URL` в `.env` можно не заполнять: `docker-compose.yml` сам подставляет адрес контейнера Postgres. Пароль в логах бота не печатается. В пароле Postgres не используйте символы `@`, `:`, `/` и `#` — они ломают адрес базы.

`REDIS_URL` оставьте пустым, если отдельного Redis нет. Состояния диалогов тогда живут в памяти процесса и сбрасываются при перезапуске контейнера. Это нормально для одного бота.

`YOOKASSA_IP_CHECK=true` можно оставить. nginx передаёт адрес клиента в `X-Forwarded-For`.

Не коммитьте `.env`.

## 5. Если есть файл SQLite

Положите его на сервер, например в `/opt/wardrobe-bot/wardrobe.sqlite3`, и откройте чтение: `chmod a+r wardrobe.sqlite3`. Поднимите Postgres и один раз прогоните скрипт. Повторный запуск не затирает строки, которые уже есть в Postgres.

```bash
cd /opt/wardrobe-bot
docker compose up -d postgres
docker compose run --rm \
  -v "$PWD/wardrobe.sqlite3:/data/wardrobe.sqlite3:ro" \
  bot python scripts/sqlite_to_postgres.py /data/wardrobe.sqlite3
```

В выводе будет `имя_таблицы: новых строк N`. Второй запуск покажет нули — так и должно быть.

Если живая база была Postgres на Render, вместо этого скрипта залейте дамп в контейнер `postgres`.

## 6. Запуск

Сначала остановите бота на Render, и только потом запускайте его здесь. Иначе Telegram будет отдавать сообщения обоим, и люди получат двойные ответы.

1. В панели Render нажмите Suspend / Stop у сервиса бота. Убедитесь, что он не в статусе Live.
2. На сервере:

```bash
cd /opt/wardrobe-bot
docker compose up -d --build
docker compose logs -f bot
```

В логах должны быть строки:

- `Storage backend: PostgreSQL host=postgres port=5432 dbname=wardrobe user=wardrobe` — без пароля
- `Telegram mode: polling`
- `HTTP server started on 0.0.0.0:10000`
- `Telegram getMe: id=... username=@wardrobe_24_bot`
- `FSM storage: MemoryStorage` (или Redis, если задали `REDIS_URL`)

Остановка просмотра логов: Ctrl+C, контейнеры при этом продолжают работать.

Проверка с сервера:

```bash
curl -sS http://127.0.0.1:10000/
```

Ответ: `OK`.

## 7. nginx и сертификат

Файл `/etc/nginx/sites-available/wardrobe-bot`:

```nginx
server {
    listen 80;
    server_name bot.shkaf-rabotaet.ru;

    location / {
        proxy_pass http://127.0.0.1:10000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/wardrobe-bot /etc/nginx/sites-enabled/wardrobe-bot
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d bot.shkaf-rabotaet.ru
```

Certbot сам допишет `listen 443 ssl` и сертификат Let's Encrypt. После этого с любой машины:

```bash
curl -sS https://bot.shkaf-rabotaet.ru/
```

снова `OK`.

Адрес для ЮKassa: `https://bot.shkaf-rabotaet.ru/yookassa/webhook`

## 8. ЮKassa

В кабинете ЮKassa смените URL уведомлений на `https://bot.shkaf-rabotaet.ru/yookassa/webhook`, событие `payment.succeeded`.

Автоплатежи и сохранение карты не включайте: бот принимает только разовую оплату.

Напишите боту в Telegram обычное сообщение и, если пользуетесь клубом, пройдите тестовый платёж на 1 ₽. В логах `docker compose logs bot` не должно быть `YooKassa webhook rejected`. Если вебхук отвечает 403 из‑за адреса прокси, в `.env` поставьте `YOOKASSA_IP_CHECK=false` и перезапустите: `docker compose up -d`. Платёж всё равно проверяется запросом в API ЮKassa, поддельное тело вебхука клуб не включит.

## 9. Откат на Render

1. `docker compose stop` в `/opt/wardrobe-bot` — VPS больше не забирает сообщения.
2. В ЮKassa верните старый URL вебхука Render.
3. В Render нажмите Resume. При старте бот снова поставит свой Telegram-вебхук (`TG_MODE` там по умолчанию `webhook`).
4. Напишите боту и убедитесь, что отвечает один раз.

Не держите Render и VPS запущенными одновременно.

## Переменные, без которых бот на VPS не взлетит

| Переменная | Зачем |
| --- | --- |
| `BOT_TOKEN` | Telegram |
| `TG_MODE=polling` | long polling; compose ставит это сам |
| `POSTGRES_PASSWORD` | пароль базы в compose |
| `PORT=10000` | порт за nginx |
| `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` | оплата |
| `AI_API_KEY` | разбор фото вещей |

`DB_URL` и `DATABASE_URL` — адрес Postgres. Пустые оба означают SQLite, на сервере так делать не нужно. `REDIS_URL` необязателен.
