# Claude Dispatcher Bot — Design Spec

Telegram-бот для удалённого управления сессиями Claude Code с телефона.
Работает локально на Windows, запускает/убивает сессии в любых проектах,
мониторит лимиты Max-подписки, шлёт уведомления, собирает аналитику использования.

## Tech Stack

- Python 3.12+
- python-telegram-bot — Telegram UI
- asyncio + subprocess — управление процессами `claude` CLI
- matplotlib — графики аналитики
- JSON-файлы — персистентность (проекты, конфигурация)
- CSV — хранение истории usage
- `https://api.anthropic.com/api/oauth/usage` — мониторинг лимитов

## Project Structure

```
claude_dispatcher/
├── bot.py                    # Точка входа, Application setup
├── config.py                 # Загрузка .env + config.json
├── handlers/
│   ├── projects.py           # Меню проектов: сканирование, добавление, удаление
│   ├── sessions.py           # Wizard запуска, список активных, убийство
│   └── settings.py           # Настройки порогов, путей
├── core/
│   ├── session_manager.py    # Запуск/убийство процессов claude, парсинг URL
│   ├── project_registry.py   # CRUD проектов, сканирование git-репо, projects.json
│   ├── limit_tracker.py      # Поллинг /api/oauth/usage, пороговые уведомления
│   └── notifier.py           # Отправка сообщений/уведомлений в Telegram
├── analytics/
│   ├── collector.py          # Периодическая запись usage → CSV
│   ├── charts.py             # matplotlib графики (day/week/heatmap)
│   └── handlers.py           # Telegram хэндлеры для команд аналитики
├── data/
│   ├── projects.json         # Зарегистрированные проекты
│   └── usage/                # CSV файлы с историей usage
├── logs/
├── .env.example
├── config.example.json
├── requirements.txt
└── .gitignore
```

## Components

### Session Manager (`core/session_manager.py`)

Управляет процессами `claude` CLI. Два режима запуска:

**Remote Control** (основной, для доступа с телефона):
```
claude --remote-control "промпт"
```
- Запускается в cwd проекта
- Парсит stdout на паттерн `https://claude.ai/code/session_...`
  (строка: `/remote-control is active. Code in CLI or at <URL>`)
- Отправляет URL в Telegram через Notifier
- Процесс живёт пока сессия активна

**Обычный** (headless, отработал и завершился):
```
claude -p --output-format json "промпт"
```
- Запускается в cwd проекта
- Парсит JSON-результат (`result`, `duration_ms`, `total_cost_usd`)
- Отправляет итог в Telegram через Notifier
- Процесс завершается сам после выполнения

**Общее для обоих режимов:**
- Бот НЕ передаёт `--permission-mode` и `--dangerously-skip-permissions` — Claude Code использует настройки из `.claude/settings.json` проекта или глобального конфига
- Хранение активных сессий в памяти: `dict[session_id, SessionInfo]`
  - SessionInfo: pid, проект, режим, время старта, asyncio.Process
- Убийство: `process.terminate()` → 5с таймаут → `process.kill()`
- Мониторинг stderr на rate limit сообщения
- Активные сессии не переживают перезапуск бота

### Project Registry (`core/project_registry.py`)

Хранит и управляет зарегистрированными проектами.

- Сканирует директорию (задаётся пользователем в `config.json`) на первый уровень, ищет папки с `.git`
- Пользователь выбирает из найденных через inline-кнопки в Telegram
- Операции: добавить, удалить, список
- Персистентность: `data/projects.json`

Формат `data/projects.json`:
```json
[
  {
    "name": "gym-tracker-bot",
    "path": "E:\\gym-tracker-bot",
    "added_at": "2026-04-10T12:00:00"
  }
]
```

### Limit Tracker (`core/limit_tracker.py`)

Мониторинг лимитов Max-подписки.

- Поллинг `GET https://api.anthropic.com/api/oauth/usage` с OAuth-токеном
- OAuth-токен читается из `~/.claude/.credentials.json` → `claudeAiOauth.accessToken`
- Токен имеет `expiresAt` — при истечении refresh через `refreshToken`
- Интервал поллинга настраивается в `config.json` (дефолт 60 сек)

Формат ответа API:
```json
{
  "five_hour": { "utilization": 0.35, "resets_at": "ISO-8601" },
  "seven_day": { "utilization": 0.12, "resets_at": "ISO-8601" },
  "seven_day_sonnet": { "utilization": 0.08, "resets_at": "ISO-8601" },
  "extra_usage": {
    "is_enabled": true,
    "monthly_limit": 10000,
    "used_credits": 500,
    "utilization": 0.05
  }
}
```

- Отслеживает `five_hour.utilization` и `seven_day.utilization`
- Пороговые уведомления при пересечении порогов (дефолт 70%, 85%, 95%)
- Каждый порог срабатывает **один раз** до сброса — не спамит

### Notifier (`core/notifier.py`)

Единая точка отправки сообщений в Telegram.

| Событие | Сообщение |
|---|---|
| Сессия запущена (remote) | `🚀 project: сессия запущена` + кликабельный URL |
| Сессия запущена (обычная) | `🚀 project: задача запущена` |
| Сессия завершилась | `✅ project: завершилась (12 мин)` |
| Сессия упала | `❌ project: ошибка` + stderr |
| Rate limit | `⏸️ project: rate limit, ожидание` |
| Лимит 70% | `⚠️ 5h лимит 70% — reset через X мин` |
| Лимит 85% | `⛔ 5h лимит 85% — рекомендую паузу` |
| Лимит 95% | `🔴 5h лимит 95% — почти исчерпан` |

- `chat_id` из `.env` (`TELEGRAM_USER_ID`)
- Получает инстанс `Bot` из python-telegram-bot при инициализации

### Analytics

**Collector** (`analytics/collector.py`):
- Limit Tracker вызывает callback collector'а после каждого поллинга, передавая свежие данные
- Collector дописывает строку в CSV
- Формат: `timestamp,five_hour_util,seven_day_util,seven_day_sonnet_util`
- Файлы по месяцам: `data/usage/2026-04.csv`
- Новый месяц = новый файл

**Charts** (`analytics/charts.py`):
- matplotlib → PNG → отправка в Telegram
- Типы графиков: дневной, недельный, тепловая карта (часы × дни недели)

**Команды** (`analytics/handlers.py`):
- `/usage` — текущий статус текстом (5h: 35%, 7d: 12%, reset через X)
- `/usage_day` — график за сутки
- `/usage_week` — график за неделю
- `/usage_heatmap` — тепловая карта по часам/дням для анализа сезонности

## Telegram UI

### Главное меню (`/start`)

```
🏠 Claude Dispatcher
├── [📂 Проекты]
├── [🚀 Новая сессия]
├── [📋 Сессии]
├── [📊 Лимиты]
└── [⚙️ Настройки]
```

### Проекты (`handlers/projects.py`)
- Список зарегистрированных → inline-кнопки
- [➕ Добавить] → сканирование → выбор из найденных
- [❌ Удалить] → выбор → подтверждение

### Новая сессия (`handlers/sessions.py`)
- Шаг 1: выбор проекта (inline-кнопки)
- Шаг 2: режим [🖥️ Remote Control] / [▶️ Обычная]
- Шаг 3: ввод промпта текстом или [/skip]
- Результат: URL в чат (remote) или ожидание завершения (обычная)
- Реализация через `ConversationHandler` из python-telegram-bot

### Активные сессии (`handlers/sessions.py`)
- Список активных с временем жизни
- [❌ Убить] на каждой

### Настройки (`handlers/settings.py`)
- Просмотр текущих порогов и интервала поллинга
- MVP: только просмотр, изменение через `config.json`

## Configuration

### `.env`
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_USER_ID=...
```

### `config.json`
```json
{
  "projects_dir": "E:\\",
  "poll_interval_sec": 60,
  "thresholds": [70, 85, 95],
  "log_level": "INFO"
}
```

### OAuth-токен
Читается напрямую из `~/.claude/.credentials.json` — не дублируется в `.env`.

## Security

- Каждый входящий Telegram update проверяет `from_user.id == TELEGRAM_USER_ID`. Остальных игнорируем молча.
- Секреты только в `.env`
- OAuth-токен из существующего файла Claude Code, не копируется
- Один бот = один пользователь. Каждый разворачивает свой инстанс.

## .gitignore
```
.env
config.json
data/
logs/
__pycache__/
venv/
*.pyc
```

## Open Questions Resolved

| Вопрос из оригинальной спеки | Ответ |
|---|---|
| Формат oauth/usage endpoint | JSON с `five_hour`, `seven_day`, `seven_day_sonnet`, `extra_usage` — каждый с `utilization` (0-1) и `resets_at` |
| OAuth-токен на Windows | `~/.claude/.credentials.json` → `claudeAiOauth.accessToken` (формат `sk-ant-oat01-...`) |
| Формат stdout remote-control | Строка `/remote-control is active. Code in CLI or at https://claude.ai/code/session_<ID>` |
| Permission prompt в stdout | Не актуально — бот не управляет разрешениями, используются настройки проекта/глобальные |
