# Claude Dispatcher — Agent Guide

## Команды

```bash
# Запуск
python bot.py

# Тесты
pytest

# Один файл
pytest tests/test_notifier.py -v
```

## Архитектура

```
bot.py                  — точка входа, собирает компоненты, регистрирует хендлеры
config.py               — загрузка .env + config.json → dataclass Config
│
├── core/               — бизнес-логика (без Telegram UI)
│   ├── notifier.py         — отправка сообщений в Telegram (форматирование, inline-кнопки)
│   ├── session_manager.py  — жизненный цикл subprocess claude CLI
│   ├── project_registry.py — CRUD проектов (JSON-хранилище)
│   ├── limit_tracker.py    — опрос rate-limit через /v1/messages, пороговые алерты
│   └── hook_server.py      — aiohttp-сервер, принимает webhook от Claude Code сессий
│
├── handlers/           — Telegram callback/command хендлеры
│   ├── auth.py             — декоратор authorized(user_id)
│   ├── sessions.py         — визард новой сессии (ConversationHandler), список/kill
│   ├── projects.py         — сканирование, добавление, удаление проектов
│   └── settings.py         — отображение текущих настроек
│
├── analytics/          — сбор и визуализация данных
│   ├── collector.py        — запись usage в CSV (помесячно)
│   ├── charts.py           — matplotlib графики (day, week, heatmap)
│   └── handlers.py         — Telegram UI для лимитов и графиков
│
├── service/            — скрипты деплоя (systemd, NSSM)
├── vscode-extension/   — VS Code/Cursor extension для IDE-интеграции
└── tests/              — pytest + pytest-asyncio
```

## Потоки данных

### Запуск сессии
```
Telegram → handlers/sessions.py → session_manager.start_remote()/start_normal()
  → subprocess claude CLI
  → (если ide != "none") пишет ~/.claude-dispatcher/terminal.json → VS Code extension
```

### Уведомления от Claude Code
```
Claude Code hooks → POST http://127.0.0.1:9384/hooks → hook_server.py
  → notifier.py → Telegram (с inline-кнопками)
```

### Мониторинг лимитов
```
limit_tracker.py (asyncio loop) → POST /v1/messages (haiku ping)
  → парсит заголовки anthropic-ratelimit-unified-*
  → при пересечении порога → notifier.limit_warning()
  → collector.record() → CSV
```

## Ключевые соглашения

- **Язык UI**: русский (все сообщения в Telegram на русском)
- **Inline-кнопки**: каждое уведомление имеет кнопку "Меню" или "Открыть сессию"
- **Callback data**: строковые константы (`main_menu`, `limits`, `new_session`, `projects`, `sessions`, `settings`, `chart_day`, `chart_week`, `chart_heatmap`)
- **Auth**: все хендлеры оборачиваются в `auth_check` (декоратор из handlers/auth.py)
- **Конфиг**: секреты в `.env`, настройки в `config.json`, никогда не коммитить реальные значения
- **IDE IPC**: файловый протокол через `~/.claude-dispatcher/` (trigger → ack)

## Хранилище данных

```
data/
├── projects.json           — [{name, path, added_at}]
├── usage/YYYY-MM.csv       — timestamp, five_hour_util, seven_day_util, seven_day_sonnet_util
├── charts/*.png            — генерируемые графики
└── .usage_backoff          — персистентный backoff при 429

logs/
└── bot.log                 — основной лог приложения
```

## Как добавить новый тип уведомления

1. Добавь метод в `core/notifier.py` с `reply_markup=_MENU_KB` или `_session_kb(url)`
2. Вызови его из нужного места (`hook_server.py`, `session_manager.py`, `limit_tracker.py`)
3. Напиши тест в `tests/test_notifier.py`

## Как добавить новый экран в Telegram UI

1. Создай хендлер-функцию в соответствующем файле `handlers/`
2. Оберни в `@auth_check`
3. Верни `CallbackQueryHandler` из `create_*_handlers()`
4. Зарегистрируй в `bot.py` через `app.add_handler()`
5. Добавь кнопку с `callback_data` на нужном экране

## Как добавить новый тип графика

1. Добавь метод `generate_*()` в `analytics/charts.py`
2. Добавь callback-хендлер в `analytics/handlers.py`
3. Добавь `InlineKeyboardButton` в `_chart_kb` и в клавиатуру `show_limits`
4. Зарегистрируй `CallbackQueryHandler` в return-списке

## Особенности платформы

- **Windows**: subprocess-ы убиваются через `taskkill /T /F /PID` (дерево процессов)
- **OAuth токены**: `~/.claude/.credentials.json`, могут 401 при race condition (обрабатывается)
- **Rate limits**: headers `anthropic-ratelimit-unified-{5h,7d}-{utilization,reset}` из /v1/messages
- **Hook port**: по умолчанию 9384, настраивается через `hook_port` в config.json
