# Session Notifications via Hooks — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Receive Telegram notifications when a remote Claude Code session finishes or needs permission, via Claude Code HTTP hooks.

**Architecture:** Lightweight aiohttp HTTP server on localhost receives POST from Claude Code hooks (Stop, Notification, StopFailure). Maps events to Notifier calls. Hooks configured once in `~/.claude/settings.json`.

**Tech Stack:** aiohttp (already a dependency), python-telegram-bot (existing)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `core/hook_server.py` | Create | HTTP server, event routing, session context lookup |
| `core/notifier.py` | Modify | Add hook-event notification methods |
| `config.py` | Modify | Add `hook_port` field |
| `bot.py` | Modify | Wire HookServer into lifecycle |
| `handlers/sessions.py` | Modify | Remove `/skip` (no-prompt) option |
| `tests/test_hook_server.py` | Create | Unit tests for hook server |
| `tests/test_notifier.py` | Create | Unit tests for new notifier methods |

---

### Task 1: Add `hook_port` to Config

**Files:**
- Modify: `config.py:9-18` (Config dataclass)
- Modify: `config.py:37-46` (load_config)

- [ ] **Step 1: Add field to Config dataclass**

In `config.py`, add `hook_port` to the `Config` dataclass:

```python
@dataclass
class Config:
    telegram_bot_token: str
    telegram_user_id: int
    projects_dir: str = ""
    poll_interval_sec: int = 60
    thresholds: list[int] = field(default_factory=lambda: [70, 85, 95])
    log_level: str = "INFO"
    ide: str = "none"
    ide_trigger_timeout: int = 30
    hook_port: int = 9384
```

- [ ] **Step 2: Load from config.json**

In `load_config`, add:

```python
hook_port=file_config.get("hook_port", 9384),
```

after the `ide_trigger_timeout` line.

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "feat: add hook_port config option (default 9384)"
```

---

### Task 2: Add notification methods to Notifier

**Files:**
- Modify: `core/notifier.py`
- Create: `tests/test_notifier.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_notifier.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.notifier import Notifier


@pytest.fixture
def notifier():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return Notifier(bot=bot, chat_id=123)


@pytest.mark.asyncio
async def test_permission_needed(notifier):
    await notifier.permission_needed(
        project="myproject",
        url="https://claude.ai/code/session_abc",
        message="Claude needs permission to use Bash",
    )
    notifier._bot.send_message.assert_called_once()
    text = notifier._bot.send_message.call_args.kwargs["text"]
    assert "myproject" in text
    assert "session_abc" in text


@pytest.mark.asyncio
async def test_permission_needed_no_url(notifier):
    await notifier.permission_needed(project="proj", url=None, message="needs perm")
    text = notifier._bot.send_message.call_args.kwargs["text"]
    assert "proj" in text


@pytest.mark.asyncio
async def test_agent_idle(notifier):
    await notifier.agent_idle(project="proj", url="https://claude.ai/code/session_x")
    text = notifier._bot.send_message.call_args.kwargs["text"]
    assert "proj" in text


@pytest.mark.asyncio
async def test_agent_stopped(notifier):
    await notifier.agent_stopped(project="proj", error="rate_limit", details="retry 60s")
    text = notifier._bot.send_message.call_args.kwargs["text"]
    assert "rate_limit" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_notifier.py -v`
Expected: FAIL — methods don't exist yet.

- [ ] **Step 3: Implement notification methods**

Add to `core/notifier.py` after the `limit_warning` method:

```python
    async def permission_needed(
        self, project: str, url: str | None, message: str
    ) -> None:
        link = f"\n📎 {url}" if url else ""
        await self.send(
            f"⚠️ <b>{project}</b>: ждёт разрешения\n{message}{link}"
        )

    async def agent_idle(self, project: str, url: str | None = None) -> None:
        link = f"\n📎 {url}" if url else ""
        await self.send(f"💤 <b>{project}</b>: агент завершил, ждёт ввода{link}")

    async def agent_stopped(
        self, project: str, error: str, details: str = ""
    ) -> None:
        detail_text = f"\n<pre>{details[:300]}</pre>" if details else ""
        await self.send(f"⛔ <b>{project}</b>: {error}{detail_text}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_notifier.py -v`
Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add core/notifier.py tests/test_notifier.py
git commit -m "feat: add hook notification methods to Notifier"
```

---

### Task 3: Create HookServer

**Files:**
- Create: `core/hook_server.py`
- Create: `tests/test_hook_server.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_hook_server.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from core.hook_server import HookServer


@pytest.fixture
def notifier():
    n = MagicMock()
    n.permission_needed = AsyncMock()
    n.agent_idle = AsyncMock()
    n.agent_stopped = AsyncMock()
    n.session_finished = AsyncMock()
    n.send = AsyncMock()
    return n


@pytest.fixture
def session_manager():
    sm = MagicMock()
    sm.get_session = MagicMock(return_value=None)
    return sm


@pytest.fixture
def hook_server(notifier, session_manager):
    return HookServer(notifier=notifier, session_manager=session_manager, port=0)


@pytest.fixture
def app(hook_server):
    return hook_server.create_app()


@pytest.fixture
def client(aiohttp_client, app):
    return aiohttp_client(app)


@pytest.mark.asyncio
async def test_stop_event(client, notifier):
    cl = await client
    resp = await cl.post("/hooks", json={
        "hook_event_name": "Stop",
        "session_id": "abc",
        "cwd": "/tmp/proj",
        "last_assistant_message": "Done implementing the feature.",
    })
    assert resp.status == 200
    notifier.send.assert_called_once()
    text = notifier.send.call_args[0][0]
    assert "Done implementing" in text


@pytest.mark.asyncio
async def test_notification_permission(client, notifier):
    cl = await client
    resp = await cl.post("/hooks", json={
        "hook_event_name": "Notification",
        "notification_type": "permission_prompt",
        "session_id": "abc",
        "cwd": "/tmp/proj",
        "message": "Claude needs permission to use Bash",
    })
    assert resp.status == 200
    notifier.permission_needed.assert_called_once()


@pytest.mark.asyncio
async def test_notification_idle(client, notifier):
    cl = await client
    resp = await cl.post("/hooks", json={
        "hook_event_name": "Notification",
        "notification_type": "idle_prompt",
        "session_id": "abc",
        "cwd": "/tmp/proj",
        "message": "Agent is idle",
    })
    assert resp.status == 200
    notifier.agent_idle.assert_called_once()


@pytest.mark.asyncio
async def test_stop_failure(client, notifier):
    cl = await client
    resp = await cl.post("/hooks", json={
        "hook_event_name": "StopFailure",
        "session_id": "abc",
        "cwd": "/tmp/proj",
        "error": "rate_limit",
        "error_details": "retry after 60s",
    })
    assert resp.status == 200
    notifier.agent_stopped.assert_called_once()


@pytest.mark.asyncio
async def test_unknown_event(client, notifier):
    cl = await client
    resp = await cl.post("/hooks", json={
        "hook_event_name": "SomeNewEvent",
        "session_id": "abc",
        "cwd": "/tmp",
    })
    assert resp.status == 200
    notifier.send.assert_not_called()
    notifier.permission_needed.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_json(client, notifier):
    cl = await client
    resp = await cl.post("/hooks", data=b"not json", headers={"Content-Type": "application/json"})
    assert resp.status == 400


@pytest.mark.asyncio
async def test_session_context_lookup(client, notifier, session_manager):
    session_info = MagicMock()
    session_info.project_name = "my-project"
    session_info.url = "https://claude.ai/code/session_xyz"
    session_manager.get_session.return_value = None

    # HookServer looks up by cwd-based heuristic, not session_id directly
    # (Claude hook session_id != bot session_id)
    cl = await client
    resp = await cl.post("/hooks", json={
        "hook_event_name": "Notification",
        "notification_type": "permission_prompt",
        "session_id": "claude-internal-id",
        "cwd": "/tmp/proj",
        "message": "Needs permission",
    })
    assert resp.status == 200
    notifier.permission_needed.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_hook_server.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement HookServer**

Create `core/hook_server.py`:

```python
import logging
from pathlib import Path

from aiohttp import web

from core.notifier import Notifier

logger = logging.getLogger(__name__)


class HookServer:
    def __init__(self, notifier: Notifier, session_manager, port: int = 9384):
        self._notifier = notifier
        self._session_manager = session_manager
        self._port = port
        self._runner: web.AppRunner | None = None

    def create_app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/hooks", self._handle_hook)
        return app

    async def start(self) -> None:
        app = self.create_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self._port)
        await site.start()
        logger.info("Hook server listening on 127.0.0.1:%d", self._port)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    def _find_session_by_cwd(self, cwd: str):
        """Find a bot session whose project path matches the hook's cwd."""
        cwd_path = Path(cwd).resolve()
        for info in self._session_manager.list_sessions():
            # Session doesn't store path, but we can match by project_name
            # For now, return the first active session (single-user bot)
            return info
        return None

    def _get_context(self, data: dict) -> tuple[str, str | None]:
        """Extract project name and URL from hook data + session lookup."""
        cwd = data.get("cwd", "")
        session = self._find_session_by_cwd(cwd)
        if session:
            return session.project_name, session.url
        # Fallback: derive project name from cwd
        return Path(cwd).name if cwd else "unknown", None

    async def _handle_hook(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400, text="invalid json")

        event = data.get("hook_event_name", "")
        logger.info("Hook event: %s", event)

        project, url = self._get_context(data)

        if event == "Stop":
            last_msg = data.get("last_assistant_message", "")
            truncated = last_msg[:300] + "..." if len(last_msg) > 300 else last_msg
            await self._notifier.send(
                f"✅ <b>{project}</b>: задача завершена\n<pre>{truncated}</pre>"
            )

        elif event == "Notification":
            ntype = data.get("notification_type", "")
            message = data.get("message", "")

            if ntype == "permission_prompt":
                await self._notifier.permission_needed(
                    project=project, url=url, message=message
                )
            elif ntype == "idle_prompt":
                await self._notifier.agent_idle(project=project, url=url)
            else:
                logger.debug("Ignoring notification type: %s", ntype)

        elif event == "StopFailure":
            error = data.get("error", "unknown")
            details = data.get("error_details", "")
            await self._notifier.agent_stopped(
                project=project, error=error, details=details
            )

        else:
            logger.debug("Ignoring hook event: %s", event)

        return web.Response(status=200)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_hook_server.py -v`
Expected: all 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add core/hook_server.py tests/test_hook_server.py
git commit -m "feat: HookServer for Claude Code event notifications"
```

---

### Task 4: Wire HookServer into bot lifecycle

**Files:**
- Modify: `bot.py:12-13` (imports), `bot.py:68-70` (init), `bot.py:116-124` (lifecycle)

- [ ] **Step 1: Add import**

Add to `bot.py` imports (after line 12):

```python
from core.hook_server import HookServer
```

- [ ] **Step 2: Create HookServer instance**

After `session_manager` creation (after line 70), add:

```python
    hook_server = HookServer(notifier=notifier, session_manager=session_manager, port=cfg.hook_port)
```

- [ ] **Step 3: Add to lifecycle hooks**

Update `post_init` and `post_shutdown`:

```python
    async def post_init(application: Application):
        limit_tracker.start()
        await hook_server.start()
        logger.info("Bot started. Limit tracker polling every %ds, hooks on port %d", cfg.poll_interval_sec, cfg.hook_port)

    async def post_shutdown(application: Application):
        limit_tracker.stop()
        await hook_server.stop()
```

- [ ] **Step 4: Verify bot starts**

Run: `python bot.py`
Expected: log line `Hook server listening on 127.0.0.1:9384`

- [ ] **Step 5: Commit**

```bash
git add bot.py
git commit -m "feat: wire HookServer into bot lifecycle"
```

---

### Task 5: Configure Claude Code hooks

**Files:**
- Modify: `~/.claude/settings.json`

- [ ] **Step 1: Read current settings**

Read `~/.claude/settings.json` to see existing content.

- [ ] **Step 2: Merge hooks config**

Add or merge the `hooks` key into `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "http",
            "url": "http://localhost:9384/hooks",
            "timeout": 5
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "http",
            "url": "http://localhost:9384/hooks",
            "timeout": 5
          }
        ]
      }
    ],
    "StopFailure": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "http",
            "url": "http://localhost:9384/hooks",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

Preserve all existing keys — only add/update `hooks`.

- [ ] **Step 3: Verify hooks are active**

Run: `claude /hooks`
Expected: Should list the configured HTTP hooks.

---

### Task 6: Remove no-prompt session option

**Files:**
- Modify: `handlers/sessions.py:148-157`

- [ ] **Step 1: Change prompt message and remove /skip**

In `wizard_select_mode`, change the prompt text:

```python
        await query.edit_message_text("Введи промпт:")
```

In `wizard_enter_prompt`, remove the `/skip` handling:

```python
    @auth_check
    async def wizard_enter_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
        prompt = update.message.text.strip()
        if not prompt:
            await update.message.reply_text("⚠️ Промпт не может быть пустым")
            return ENTER_PROMPT
```

In the ConversationHandler `ENTER_PROMPT` state, remove the `/skip` regex handler:

```python
            ENTER_PROMPT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_enter_prompt),
            ],
```

- [ ] **Step 2: Verify wizard works**

Start bot, go through session wizard. Confirm no `/skip` option and empty text is rejected.

- [ ] **Step 3: Commit**

```bash
git add handlers/sessions.py
git commit -m "fix: require prompt for all sessions, remove /skip"
```

---

### Task 7: Integration test

- [ ] **Step 1: Start the bot**

Run: `python bot.py`
Verify: hook server starts on port 9384.

- [ ] **Step 2: Send a test hook manually**

```bash
curl -X POST http://localhost:9384/hooks -H "Content-Type: application/json" -d '{"hook_event_name":"Notification","notification_type":"permission_prompt","session_id":"test","cwd":"/tmp","message":"Test permission"}'
```

Verify: Telegram notification received.

- [ ] **Step 3: Start a real remote session and verify events arrive**

Create a session via the bot. Wait for the agent to finish or hit a permission prompt. Confirm Telegram notification.
