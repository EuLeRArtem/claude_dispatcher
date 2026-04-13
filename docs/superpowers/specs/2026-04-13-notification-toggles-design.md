# Notification Toggles — Design Spec

## Summary

Add per-category notification toggles to the Telegram bot, controllable from the Settings screen via inline buttons.

## Categories

| Category | Notifier methods | Callback data | Default |
|---|---|---|---|
| Sessions | `session_started`, `session_finished`, `session_error`, `agent_stopped`, hook `Stop` | `toggle_sessions` | on |
| Limits | `limit_warning`, `cost_warning` | `toggle_limits` | on |
| Permissions | `permission_needed`, `agent_idle` | `toggle_permissions` | on |

### Force override

`permission_needed` always sends regardless of the Permissions toggle state — it blocks the session and missing it is costly.

## Storage

File: `data/notifications.json`

```json
{"sessions": true, "limits": true, "permissions": true}
```

- Bot reads on startup, writes on each toggle.
- If file is missing — all categories default to `true`.
- Separate from `config.json` (static config) since toggles are runtime state changed from Telegram UI.

## UI

Three toggle buttons added to the existing Settings screen (`handlers/settings.py`):

```
⚙️ Настройки

📁 Директория проектов: E:\projects
⏱️ Интервал поллинга: 60 сек
📊 Пороги: 70%, 85%, 95%
🖥️ IDE: cursor (таймаут триггера: 30 сек)
📝 Уровень логов: INFO

🔔 Уведомления:
  Сессии: вкл | Лимиты: вкл | Разрешения: выкл

[🔔 Сессии] [🔔 Лимиты] [🔕 Разрешения]
[🔙 Назад]
```

Button press: inverts the category state, saves to JSON, redraws the Settings screen with updated icons.

## Architecture

### New: `core/notification_settings.py`

Class `NotificationSettings`:
- `__init__(path="data/notifications.json")` — loads state from file (defaults to all-on)
- `is_enabled(category: str) -> bool` — check if category is on
- `toggle(category: str) -> bool` — flip state, save to disk, return new value
- `all_states() -> dict[str, bool]` — for rendering UI

### Modified: `core/notifier.py`

- `Notifier.__init__` receives optional `NotificationSettings` reference
- Each send method checks `is_enabled(category)` before sending
- `permission_needed` skips the check (force override)

Category mapping in Notifier:
- `session_started`, `session_finished`, `session_error` → `"sessions"`
- `agent_stopped` → `"sessions"`
- `limit_warning`, `cost_warning` → `"limits"`
- `permission_needed` → force (no check)
- `agent_idle` → `"permissions"`

### Modified: `handlers/settings.py`

- Three new `CallbackQueryHandler`s for `toggle_sessions`, `toggle_limits`, `toggle_permissions`
- Updated `show_settings` to display toggle states and buttons
- `NotificationSettings` accessed via `context.bot_data["notification_settings"]`

### Modified: `core/hook_server.py`

Hook `Stop` sends via `self._notifier.send()` directly — needs to check `is_enabled("sessions")` before sending, or route through a Notifier method that does the check.

### Modified: `bot.py`

- Create `NotificationSettings` instance
- Pass to `Notifier` constructor
- Store in `bot_data["notification_settings"]`

## Data flow

### Toggle
```
Button [🔔 Лимиты] → toggle_limits handler
  → NotificationSettings.toggle("limits")
  → write data/notifications.json
  → redraw Settings screen (🔕 Лимиты)
```

### Notification filtering
```
Event limit_warning → Notifier.limit_warning()
  → settings.is_enabled("limits") → False → skip (log at DEBUG)

Event permission_needed → Notifier.permission_needed()
  → no check → always sends
```

## Testing

- Unit tests for `NotificationSettings` (load, save, toggle, defaults)
- Unit tests for `Notifier` with settings mock (verify skip when disabled, verify force override for `permission_needed`)
- Test toggle handler (callback → state change → UI update)
