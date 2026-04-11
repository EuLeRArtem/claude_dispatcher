# Session Event Notifications via Claude Code Hooks

**Date:** 2026-04-11
**Status:** Approved

## Problem

Remote-control sessions (`claude --remote-control`) don't send push notifications to the phone app when the agent finishes or needs permission. The user has to keep checking the browser manually.

## Solution

Use Claude Code's built-in HTTP hooks system. The bot runs a lightweight HTTP server on localhost. Claude Code POSTs events to it. The bot forwards them as Telegram notifications.

## Architecture

```
Claude CLI (--remote-control)
  | hook fires (Stop, Notification, StopFailure)
  v
POST localhost:{hook_port}/hooks
  |
  v
HookServer (aiohttp)
  | maps event -> notification
  v
Notifier -> Telegram
```

## Components

### 1. `core/hook_server.py`

Minimal aiohttp web server. Single endpoint `POST /hooks`.

**Event mapping:**

| hook_event_name | condition | Telegram message |
|---|---|---|
| Notification | notification_type=permission_prompt | "Waiting for permission — open session" + URL |
| Notification | notification_type=idle_prompt | "Agent finished, waiting for input" |
| Stop | * | "Task completed" + truncated last_assistant_message |
| StopFailure | error=rate_limit | "Rate limit, agent stopped" |
| StopFailure | other | "Error: {error}" |

**Session context:** Extract `session_id` from POST body, look up in `SessionManager._sessions` to add project name and session URL. If session not found, send notification without context.

**Response:** Empty 200 immediately. Claude Code waits synchronously, so must be fast.

### 2. Hook configuration

One-time setup in `~/.claude/settings.json`. Bot auto-configures on first start (merges with existing settings):

```json
{
  "hooks": {
    "Stop": [{"matcher": "", "hooks": [{"type": "http", "url": "http://localhost:9384/hooks", "timeout": 5}]}],
    "Notification": [{"matcher": "", "hooks": [{"type": "http", "url": "http://localhost:9384/hooks", "timeout": 5}]}],
    "StopFailure": [{"matcher": "", "hooks": [{"type": "http", "url": "http://localhost:9384/hooks", "timeout": 5}]}]
  }
}
```

Port is configurable via `config.json` (`hook_port`, default 9384).

### 3. Integration in bot.py

```python
hook_server = HookServer(notifier, session_manager, port=cfg.hook_port)
# post_init:
await hook_server.start()
# post_shutdown:
await hook_server.stop()
```

### 4. Config changes

- `config.json`: add `hook_port` (default: 9384)
- `Config` dataclass: add `hook_port: int = 9384`

### 5. Notifier changes

Add new methods:
- `permission_needed(project, url, message)` — permission prompt notification
- `agent_idle(project, url)` — agent finished, waiting for input
- `agent_stopped(project, error, details)` — StopFailure notification

### 6. Tests

- Unit test: POST with different event types -> verify Notifier called with correct text
- Unknown event -> 200, no notification
- Invalid JSON -> 400
- Session lookup: with and without matching session_id

## Side change

Remove the ability to start sessions without a prompt (user requested).
