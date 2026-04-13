# Notification Toggles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-category notification toggles (sessions, limits, permissions) controllable from the Telegram Settings screen.

**Architecture:** New `NotificationSettings` class handles persistence to `data/notifications.json`. `Notifier` checks settings before sending. Settings UI gets toggle buttons. `permission_needed` always sends (force override).

**Tech Stack:** Python, python-telegram-bot, pytest, pytest-asyncio

---

### Task 1: NotificationSettings — tests and implementation

**Files:**
- Create: `core/notification_settings.py`
- Create: `tests/test_notification_settings.py`

- [ ] **Step 1: Write failing tests for NotificationSettings**

```python
# tests/test_notification_settings.py
import json
import pytest
from core.notification_settings import NotificationSettings


@pytest.fixture
def settings_file(tmp_path):
    return str(tmp_path / "notifications.json")


def test_defaults_when_no_file(settings_file):
    ns = NotificationSettings(path=settings_file)
    assert ns.is_enabled("sessions") is True
    assert ns.is_enabled("limits") is True
    assert ns.is_enabled("permissions") is True


def test_all_states(settings_file):
    ns = NotificationSettings(path=settings_file)
    assert ns.all_states() == {"sessions": True, "limits": True, "permissions": True}


def test_toggle_disables(settings_file):
    ns = NotificationSettings(path=settings_file)
    result = ns.toggle("limits")
    assert result is False
    assert ns.is_enabled("limits") is False


def test_toggle_enables(settings_file):
    ns = NotificationSettings(path=settings_file)
    ns.toggle("limits")  # disable
    result = ns.toggle("limits")  # enable
    assert result is True
    assert ns.is_enabled("limits") is True


def test_persists_to_disk(settings_file):
    ns = NotificationSettings(path=settings_file)
    ns.toggle("sessions")
    # Re-read from disk
    ns2 = NotificationSettings(path=settings_file)
    assert ns2.is_enabled("sessions") is False
    assert ns2.is_enabled("limits") is True


def test_loads_existing_file(settings_file):
    with open(settings_file, "w") as f:
        json.dump({"sessions": False, "limits": True, "permissions": False}, f)
    ns = NotificationSettings(path=settings_file)
    assert ns.is_enabled("sessions") is False
    assert ns.is_enabled("permissions") is False


def test_unknown_category_returns_true(settings_file):
    ns = NotificationSettings(path=settings_file)
    assert ns.is_enabled("unknown_category") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_notification_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.notification_settings'`

- [ ] **Step 3: Implement NotificationSettings**

```python
# core/notification_settings.py
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULTS = {"sessions": True, "limits": True, "permissions": True}


class NotificationSettings:
    def __init__(self, path: str = "data/notifications.json"):
        self._path = Path(path)
        self._state: dict[str, bool] = self._load()

    def _load(self) -> dict[str, bool]:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {k: data.get(k, True) for k in _DEFAULTS}
            except Exception:
                logger.warning("Failed to load %s, using defaults", self._path)
        return dict(_DEFAULTS)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._state, f)

    def is_enabled(self, category: str) -> bool:
        return self._state.get(category, True)

    def toggle(self, category: str) -> bool:
        self._state[category] = not self._state.get(category, True)
        self._save()
        return self._state[category]

    def all_states(self) -> dict[str, bool]:
        return dict(self._state)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_notification_settings.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/notification_settings.py tests/test_notification_settings.py
git commit -m "feat: add NotificationSettings with persistence"
```

---

### Task 2: Notifier — add settings check to send methods

**Files:**
- Modify: `core/notifier.py`
- Modify: `tests/test_notifier.py`

- [ ] **Step 1: Write failing tests for notification filtering**

Append to `tests/test_notifier.py`:

```python
from unittest.mock import MagicMock
from core.notification_settings import NotificationSettings


@pytest.fixture
def mock_settings():
    s = MagicMock(spec=NotificationSettings)
    s.is_enabled = MagicMock(return_value=True)
    return s


@pytest.fixture
def notifier_with_settings(bot, mock_settings):
    return Notifier(bot=bot, chat_id=123, settings=mock_settings)


@pytest.mark.asyncio
async def test_session_started_skipped_when_disabled(notifier_with_settings, bot, mock_settings):
    mock_settings.is_enabled.return_value = False
    await notifier_with_settings.session_started(project="proj", mode="normal")
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_limit_warning_skipped_when_disabled(notifier_with_settings, bot, mock_settings):
    mock_settings.is_enabled.return_value = False
    await notifier_with_settings.limit_warning(period="5h", percent=70, reset_minutes=10)
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_permission_needed_always_sends(notifier_with_settings, bot, mock_settings):
    mock_settings.is_enabled.return_value = False
    await notifier_with_settings.permission_needed(project="proj", url=None, message="needs perm")
    bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_agent_idle_skipped_when_disabled(notifier_with_settings, bot, mock_settings):
    mock_settings.is_enabled.return_value = False
    await notifier_with_settings.agent_idle(project="proj")
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notifier_works_without_settings(bot):
    """Existing Notifier without settings still sends everything."""
    n = Notifier(bot=bot, chat_id=123)
    await n.limit_warning(period="5h", percent=70, reset_minutes=10)
    bot.send_message.assert_called_once()
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `pytest tests/test_notifier.py -v`
Expected: New tests FAIL — `TypeError: Notifier.__init__() got an unexpected keyword argument 'settings'`

- [ ] **Step 3: Modify Notifier to check settings**

Update `core/notifier.py`. Changes:

1. Add `settings` parameter to `__init__`:

```python
from core.notification_settings import NotificationSettings
```

```python
class Notifier:
    def __init__(self, bot: Bot, chat_id: int, settings: NotificationSettings | None = None):
        self._bot = bot
        self._chat_id = chat_id
        self._settings = settings
```

2. Add helper method:

```python
    def _is_enabled(self, category: str) -> bool:
        if self._settings is None:
            return True
        return self._settings.is_enabled(category)
```

3. Add check at the top of each method (before building text):

- `session_started`: `if not self._is_enabled("sessions"): return`
- `session_finished`: `if not self._is_enabled("sessions"): return`
- `session_error`: `if not self._is_enabled("sessions"): return`
- `rate_limit`: `if not self._is_enabled("sessions"): return`
- `limit_warning`: `if not self._is_enabled("limits"): return`
- `cost_warning`: `if not self._is_enabled("limits"): return`
- `permission_needed`: NO CHECK (force override)
- `agent_idle`: `if not self._is_enabled("permissions"): return`
- `agent_stopped`: `if not self._is_enabled("sessions"): return`

- [ ] **Step 4: Run all notifier tests**

Run: `pytest tests/test_notifier.py -v`
Expected: All tests PASS (old + new)

- [ ] **Step 5: Commit**

```bash
git add core/notifier.py tests/test_notifier.py
git commit -m "feat: notifier checks notification settings before sending"
```

---

### Task 3: Hook server — filter Stop event through Notifier

**Files:**
- Modify: `core/hook_server.py`
- Modify: `core/notifier.py`

The hook `Stop` handler calls `self._notifier.send()` directly, bypassing the category check. Route it through a proper Notifier method instead.

- [ ] **Step 1: Add `task_completed` method to Notifier**

Append to `core/notifier.py`:

```python
    async def task_completed(self, project: str, summary: str) -> None:
        if not self._is_enabled("sessions"):
            return
        await self.send(
            f"✅ <b>{project}</b>: задача завершена\n<pre>{summary}</pre>",
            reply_markup=_MENU_KB,
        )
```

- [ ] **Step 2: Update hook_server.py Stop handler to use new method**

In `core/hook_server.py`, replace the `Stop` event block:

Old code:
```python
        if event == "Stop":
            last_msg = data.get("last_assistant_message", "")
            truncated = last_msg[:300] + "..." if len(last_msg) > 300 else last_msg
            from core.notifier import _MENU_KB
            await self._notifier.send(
                f"✅ <b>{project}</b>: задача завершена\n<pre>{truncated}</pre>",
                reply_markup=_MENU_KB,
            )
```

New code:
```python
        if event == "Stop":
            last_msg = data.get("last_assistant_message", "")
            truncated = last_msg[:300] + "..." if len(last_msg) > 300 else last_msg
            await self._notifier.task_completed(project=project, summary=truncated)
```

- [ ] **Step 3: Run existing hook server tests**

Run: `pytest tests/test_hook_server.py tests/test_notifier.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add core/notifier.py core/hook_server.py
git commit -m "refactor: route hook Stop through Notifier.task_completed"
```

---

### Task 4: Settings UI — toggle buttons

**Files:**
- Modify: `handlers/settings.py`

- [ ] **Step 1: Update settings handler with toggle buttons**

Replace `handlers/settings.py` entirely:

```python
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

logger = logging.getLogger(__name__)

CB_SETTINGS = "settings"
CB_BACK_MAIN = "main_menu"
CB_TOGGLE_SESSIONS = "toggle_sessions"
CB_TOGGLE_LIMITS = "toggle_limits"
CB_TOGGLE_PERMISSIONS = "toggle_permissions"

_LABELS = {
    "sessions": "Сессии",
    "limits": "Лимиты",
    "permissions": "Разрешения",
}


def _toggle_icon(enabled: bool) -> str:
    return "🔔" if enabled else "🔕"


def _build_settings_text(cfg, states: dict[str, bool]) -> str:
    notif_lines = " | ".join(
        f"{_LABELS[k]}: {'вкл' if v else 'выкл'}" for k, v in states.items()
    )
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"📁 Директория проектов: <code>{cfg.projects_dir or 'не задана'}</code>\n"
        f"⏱️ Интервал поллинга: {cfg.poll_interval_sec} сек\n"
        f"📊 Пороги: {', '.join(str(t) + '%' for t in cfg.thresholds)}\n"
        f"🖥️ IDE: {cfg.ide} (таймаут триггера: {cfg.ide_trigger_timeout} сек)\n"
        f"📝 Уровень логов: {cfg.log_level}\n\n"
        f"🔔 <b>Уведомления:</b>\n  {notif_lines}\n\n"
        "<i>Конфигурация: config.json | Уведомления: кнопки ниже</i>"
    )


def _build_keyboard(states: dict[str, bool]) -> InlineKeyboardMarkup:
    toggles = [
        InlineKeyboardButton(
            f"{_toggle_icon(states[k])} {_LABELS[k]}",
            callback_data=f"toggle_{k}",
        )
        for k in _LABELS
    ]
    return InlineKeyboardMarkup([
        toggles,
        [InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)],
    ])


async def _render_settings(query, context):
    cfg = context.bot_data.get("config")
    ns = context.bot_data.get("notification_settings")
    states = ns.all_states()
    await query.edit_message_text(
        _build_settings_text(cfg, states),
        reply_markup=_build_keyboard(states),
        parse_mode="HTML",
    )


def create_settings_handlers(auth_check):

    @auth_check
    async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await _render_settings(query, context)

    @auth_check
    async def handle_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        category = query.data.replace("toggle_", "")
        ns = context.bot_data.get("notification_settings")
        new_state = ns.toggle(category)
        label = _LABELS.get(category, category)
        icon = _toggle_icon(new_state)
        await query.answer(f"{icon} {label}: {'вкл' if new_state else 'выкл'}")
        await _render_settings(query, context)

    return [
        CallbackQueryHandler(show_settings, pattern=f"^{CB_SETTINGS}$"),
        CallbackQueryHandler(handle_toggle, pattern=r"^toggle_(sessions|limits|permissions)$"),
    ]
```

- [ ] **Step 2: Run bot to verify UI renders**

Run: `python bot.py` — go to Settings in Telegram, verify toggle buttons appear and work.
(Bot won't start yet — need Task 5 wiring first. Skip manual test until after Task 5.)

- [ ] **Step 3: Commit**

```bash
git add handlers/settings.py
git commit -m "feat: add notification toggle buttons to Settings UI"
```

---

### Task 5: Wire NotificationSettings into bot.py

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Add import and create instance**

Add import at top of `bot.py`:

```python
from core.notification_settings import NotificationSettings
```

After `auth_check = authorized(...)` line, create the instance:

```python
    notification_settings = NotificationSettings()
```

- [ ] **Step 2: Pass to Notifier**

Change the Notifier creation:

```python
    notifier = Notifier(bot=bot_instance, chat_id=cfg.telegram_user_id, settings=notification_settings)
```

- [ ] **Step 3: Store in bot_data**

After `app.bot_data["config"] = cfg`, add:

```python
    app.bot_data["notification_settings"] = notification_settings
```

- [ ] **Step 4: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 5: Manual smoke test**

Run: `python bot.py`
1. Open Telegram → /start → Settings
2. See toggle buttons with 🔔
3. Tap "🔔 Лимиты" → icon flips to 🔕, toast says "🔕 Лимиты: выкл"
4. Check `data/notifications.json` was created with `{"sessions": true, "limits": false, "permissions": true}`
5. Restart bot — settings persist

- [ ] **Step 6: Commit**

```bash
git add bot.py
git commit -m "feat: wire NotificationSettings into bot lifecycle"
```
