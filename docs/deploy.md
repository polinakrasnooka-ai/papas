# Как развернуть бота в Telegram

Схема:

```
GitHub Actions (cron 06:00 UTC)
    └─ python -m scripts.run
         ├─ TED API → свежие тендеры по CPV 14212*/44921* в приоритетных странах
         ├─ SQLite дедуп (state.sqlite в репо)
         ├─ Claude API → квалификация + бизнес-brief
         └─ Telegram Bot API → канал
```

Один раз настроил — дальше работает само. Разовая стоимость — $0.
Операционная: ~$0.02–0.10 в день на Claude API (несколько запросов Sonnet).
GitHub Actions для публичного/приватного репо на бесплатном плане — хватит.

## 1. Создать Telegram-бот и канал

### 1.1 Бот
1. Открой Telegram, найди `@BotFather`
2. `/newbot` → имя (например `limestone-leads-bot`), юзернейм (например `polinas_limestone_bot`)
3. BotFather пришлёт **токен** в виде `123456789:ABCdefGhIJKlmNoPQRstuVWxyz` — сохрани
4. `/setdescription` → описание (опционально)

### 1.2 Канал
1. Создай новый канал в Telegram (можно приватный)
2. Открой настройки канала → **Administrators** → **Add Administrator**
3. Найди своего бота по юзернейму → добавь, дай право **Post messages**
4. Получи ID канала:
   - Если канал публичный с юзернеймом: `TELEGRAM_CHANNEL_ID` = `@your_channel_name`
   - Если приватный: напиши что-то в канале, перешли сообщение боту `@username_to_id_bot` или `@getidsbot` — он покажет `-1001234567890` (всегда начинается с `-100`)

### 1.3 Проверка
Из терминала (локально у себя или в GitHub Actions sandbox):
```bash
TOKEN="123456789:ABC..."
CHAT="-1001234567890"  # или "@your_channel_name"
curl -s "https://api.telegram.org/bot$TOKEN/sendMessage" \
  -d chat_id="$CHAT" -d text="test from limestone-leads"
```
Если видишь сообщение в канале — всё работает.

## 2. Получить Anthropic API key

1. Открой https://console.anthropic.com/settings/keys
2. **Create Key** → назови `limestone-leads` → скопируй ключ `sk-ant-api03-…`
3. Положи $5–10 на баланс (https://console.anthropic.com/settings/billing)
4. Прикинь, что Sonnet 5.5: ~$3 / 1M input, ~$15 / 1M output. Один brief ≈ 2000 input + 500 output = $0.014. 50 новых тендеров в день = $0.70/день = $21/мес максимум. Реально будет в 5–10 раз меньше, потому что большинство попадёт в SKIP.

## 3. Положить секреты в GitHub

1. Открой https://github.com/polinakrasnooka-ai/papas/settings/secrets/actions
2. **New repository secret** → добавь по очереди:
   - `ANTHROPIC_API_KEY` = `sk-ant-api03-…`
   - `TELEGRAM_BOT_TOKEN` = `123456789:ABC…`
   - `TELEGRAM_CHANNEL_ID` = `-1001234567890` или `@your_channel_name`

Опционально через Variables (не Secrets):
- `ANTHROPIC_MODEL` = `claude-sonnet-5-5` (по умолчанию) или `claude-opus-5-5` для качества

## 4. Включить workflow

1. Открой https://github.com/polinakrasnooka-ai/papas/actions
2. Если Actions выключены — включи («I understand my workflows, go ahead»)
3. Выбери workflow **Daily TED limestone watch**
4. Нажми **Run workflow** → ветка `main` (или твоя дефолтная) → **Run**
5. Через 1–3 минуты смотри логи. Если всё ОК — к концу дня проверь канал.

Дальше он сам будет срабатывать каждый день в 06:00 UTC (09:00 Киев).

## 5. Отладка

### Сообщений в канале нет
- Проверь логи последнего run'а в Actions: tab **Daily TED limestone watch** → последний запуск → **run limestone watch**
- Если `missing env vars` — секреты не заданы, см. пункт 3
- Если `TED fetch failed` — проверь, что TED API доступен (может быть временный аутейдж)
- Если `telegram error 403: Forbidden` — бот не админ канала или неверный `chat_id`
- Если `telegram error 400: chat not found` — опечатка в `TELEGRAM_CHANNEL_ID`

### Слишком много / слишком мало сообщений
- `LOOKBACK_DAYS` в workflow (по умолчанию 7) — расширить/сузить окно поиска
- `MAX_NOTICES_PER_RUN` (по умолчанию 50) — ограничение верхней планки
- Правила скоринга в `docs/scoring.md` — ужесточить порог (сейчас 65)

### Нужно почистить дедуп
Удали `state.sqlite` из репо и запушь, следующий run заново пройдёт всё окно.

## 6. Как расширить

- **Национальные порталы**: добавить модули в `scripts/sources/` (SEAP, EKR, NEN).
  У каждого свой API/парсинг — делать по одному по мере спроса.
- **Корпоративные supplier portals**: большинство требуют авторизации, API нет.
  Проще слать в канал ссылку на supplier portal и регистрироваться вручную.
- **Еженедельный digest**: добавить второй workflow с cron `0 7 * * 1` и запросом
  к Claude «собери топ-10 за неделю из state.sqlite».
- **Фильтры по странам/категориям**: отредактируй `PRIORITY_COUNTRIES_ISO3`,
  `PRIORITY_CPV`, `PRODUCT_KEYWORDS` в `scripts/config.py`.

## 7. Что бот НЕ делает

- Не рассылает письма покупателям.
- Не регистрируется за тебя на SWPP2 / SEAP / Ariba.
- Не угадывает контакты. Там, где контакт procurement-менеджера не найден в
  первичном источнике — агент пишет «не подтверждено».
- Не ставит «UA допуск: ДА» без прямого подтверждения в SIWZ.
