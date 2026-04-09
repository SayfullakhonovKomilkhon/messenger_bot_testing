# Тестирование бота мессенджера

Два компонента:

1. **`test_client.py`** — локально дергает все методы Bot API (`/me`, диалоги, сообщения, вебхук, опционально отправка).
2. **`webhook_server.py`** + **`reply_logic.py`** — сервис для **Railway**: POST `/webhook` → ответы по простым правилам (привет, «как дела», запрос номера, распознавание RU-телефона в тексте). При `ECHO_REPLY=0` ответы отключены.

**Не как в Telegram:** API мессенджера не поддерживает inline-кнопки и «Поделиться контактом» — только текст (и файлы). Номер пользователь присылает сообщением.

## Безопасность

- **Не коммитьте** файл `.env` и **не вставляйте токен в код**. Токен из чата/скринов лучше **перевыпустить** в приложении (регенерация токена бота), если его кто-то мог увидеть.
- На Railway задавайте секреты в **Variables**, не в репозитории.

## Локально: проверка API

```bash
cd tg-bot-testing
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

В `.env` укажите:

- `MESSENGER_API_URL` — **публичный URL bot-gateway** для вызовов `/api/v1/bot/*` (без `/api/v1` в конце; скрипт сам добавит путь). Пример локально: `http://127.0.0.1:3001`. Ядро на `:3000` эти маршруты больше не отдаёт; CRUD ботов (`/api/v1/bots`) по-прежнему на ядре, если понадобится отдельный скрипт — задайте другой базовый URL вручную.
- `BOT_TOKEN` — токен бота.

Опционально:

- `TARGET_USER_ID` — UUID **человека** (не бота), чтобы проверить `startConversation`.
- `CONVERSATION_ID` — UUID чата с ботом, если список диалогов пуст с точки зрения API.
- `WEBHOOK_PUBLIC_URL` — после деплоя вебхука, например `https://xxx.up.railway.app/webhook`.
- `TEST_SEND_MESSAGE=1` — отправить тестовую строку в `CONVERSATION_ID` (осторожно: реальное сообщение в чат).

Запуск:

```bash
python test_client.py
```

В выводе будет `OK` / `FAIL` по каждому вызову.

## Railway: вебхук + эхо

1. Создайте проект из этой папки (`tg-bot-testing` как root).
2. **Variables:**
   - `MESSENGER_API_URL`
   - `BOT_TOKEN`
   - `ECHO_REPLY` = `1` (или `0`, чтобы только логировать входящие POST без ответа)
3. После деплоя скопируйте публичный URL сервиса, например `https://your-service.up.railway.app`.
4. Установите вебхук (один из способов):
   - в `.env` локально: `WEBHOOK_PUBLIC_URL=https://your-service.up.railway.app/webhook` и снова `python test_client.py`,  
   - или в приложении мессенджера укажите тот же URL вебхука для бота.
5. Напишите боту из приложения — на Railway в логах должен появиться payload; при `ECHO_REPLY=1` бот ответит строкой `[bot-test] Получено: ...`.

Проверка живости сервиса: `GET /health`.

## Пути

| Endpoint | Назначение |
|----------|------------|
| `GET /health` | Health check |
| `POST /webhook` | URL для поля вебхука бота в мессенджере |

Подробная спецификация API бота: `messenger/docs/BOT_INTEGRATION_GUIDE.md`.
# messenger_bot_testing
