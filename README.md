# Claude Dispatcher

Telegram-бот для удалённого управления [Claude Code](https://docs.anthropic.com/en/docs/claude-code) сессиями с телефона.

## Какую проблему решает

Claude Code — CLI-инструмент, работающий в терминале. Если ты запустил сессию на рабочем компьютере и ушёл — нет способа узнать, что агент остановился, достиг лимита или ждёт разрешения. Claude Dispatcher решает это:

- **Запуск сессий с телефона** — выбираешь проект, режим, пишешь промпт — сессия стартует на компьютере
- **Уведомления в реальном времени** — завершение, ошибки, запросы разрешений, rate limit
- **Мониторинг лимитов** — отслеживание 5h/7d утилизации Max-подписки с настраиваемыми порогами оповещений
- **Аналитика** — графики использования по дням, неделям и heatmap по часам

Один бот = один пользователь. Каждый разворачивает свой инстанс.

## Стек

| Компонент | Технология |
|-----------|-----------|
| Бот | [python-telegram-bot](https://python-telegram-bot.org/) 21.x |
| Hook-сервер | [aiohttp](https://docs.aiohttp.org/) (принимает webhooks от Claude Code) |
| Графики | [matplotlib](https://matplotlib.org/) + numpy |
| Конфиг | `.env` (секреты) + `config.json` (настройки) |
| IDE-интеграция | VS Code / Cursor extension (file-based IPC) |
| Автозапуск | systemd (Linux) / Task Scheduler (Windows) |

## Быстрый старт

### 1. Клонирование и зависимости

```bash
git clone <repo-url> claude-dispatcher
cd claude-dispatcher
python -m venv venv
source venv/bin/activate      # Linux/macOS
# venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

### 2. Конфигурация

```bash
cp .env.example .env
cp config.example.json config.json
```

`.env` — секреты:
```env
TELEGRAM_BOT_TOKEN=<токен от @BotFather>
TELEGRAM_USER_ID=<твой ID, узнать у @userinfobot>
```

`config.json` — настройки:
```json
{
  "projects_dir": "/home/user/projects",
  "poll_interval_sec": 60,
  "thresholds": [70, 85, 95],
  "log_level": "INFO",
  "ide": "none",
  "ide_trigger_timeout": 30,
  "hook_port": 9384
}
```

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `projects_dir` | Корневая папка для сканирования git-репозиториев | `""` |
| `poll_interval_sec` | Интервал опроса лимитов (сек) | `60` |
| `thresholds` | Пороги уведомлений (%) | `[70, 85, 95]` |
| `ide` | IDE-интеграция: `"vscode"`, `"cursor"`, `"none"` | `"none"` |
| `hook_port` | Порт для приёма webhook-ов от Claude Code | `9384` |

### 3. Настройка хуков Claude Code

Добавь в `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "http",
        "url": "http://127.0.0.1:9384/hooks"
      }
    ],
    "Notification": [
      {
        "type": "http",
        "url": "http://127.0.0.1:9384/hooks"
      }
    ],
    "StopFailure": [
      {
        "type": "http",
        "url": "http://127.0.0.1:9384/hooks"
      }
    ]
  }
}
```

### 4. Запуск

```bash
python bot.py
```

Открой бот в Telegram — `/start`.

### 5. Автозапуск (опционально)

**Linux (systemd):**
```bash
sudo bash service/install-linux.sh
```

**Windows (Task Scheduler):**

Автоматически (PowerShell от администратора):
```powershell
cd E:\claude_dispatcher
.\service\install-windows.ps1
```

Или вручную через GUI:
1. `Win+R` → `taskschd.msc` → **Создать задачу**
2. **Общие**: имя `ClaudeDispatcher`, выбрать «Запускать только для зарегистрированного пользователя»
3. **Триггеры**: Новый → **При входе в систему** → конкретный пользователь
4. **Действия**: Новый →
   - Программа: `E:\claude_dispatcher\venv\Scripts\pythonw.exe` (путь к pythonw в venv)
   - Аргументы: `bot.py`
   - Рабочая папка: `E:\claude_dispatcher`
5. **Условия**: снять «Запускать только при питании от сети»
6. **Параметры**: снять «Останавливать задачу, выполняемую дольше», включить «При сбое перезапускать через 1 мин» (до 3 раз)

> **Важно:** используется `pythonw.exe` (не `python.exe`) — окно консоли не появляется. Задача должна работать в интерактивной сессии пользователя, чтобы IDE-интеграция (VS Code/Cursor) могла открывать окна.

Управление из PowerShell:
```powershell
Start-ScheduledTask -TaskName ClaudeDispatcher      # запуск
Stop-ScheduledTask -TaskName ClaudeDispatcher       # остановка
Get-ScheduledTask -TaskName ClaudeDispatcher | Select State  # статус
Unregister-ScheduledTask -TaskName ClaudeDispatcher  # удаление
```

## IDE-интеграция

При `ide: "vscode"` или `"cursor"` бот открывает сессии во встроенном терминале IDE через VS Code extension.

**Установка из .vsix (рекомендуется):**

1. Собери пакет (если ещё не собран):
   ```bash
   cd vscode-extension
   npm install && npm run compile && npm run package
   ```
2. В VS Code / Cursor: `Ctrl+Shift+P` → **Extensions: Install from VSIX...** → выбери `vscode-extension/claude-dispatcher-terminal-0.1.0.vsix`
3. Перезагрузи IDE

**Или для разработки:**

1. Открой папку `vscode-extension/` в VS Code
2. `npm install && npm run compile`
3. F5 для запуска в режиме отладки

Extension следит за триггер-файлами в `~/.claude-dispatcher/` и автоматически открывает терминалы.

## Тесты

```bash
pytest
```

## Лицензия

MIT
