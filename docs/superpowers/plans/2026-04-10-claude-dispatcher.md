# Claude Dispatcher Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram bot that remotely manages Claude Code sessions, monitors Max subscription limits, and collects usage analytics.

**Architecture:** Modular Python app with `core/` for business logic (session management, project registry, limit tracking, notifications), `handlers/` for Telegram UI, and `analytics/` for usage data collection and charting. All components are wired together in `bot.py` entry point.

**Tech Stack:** Python 3.12+, python-telegram-bot 21.x, asyncio, aiohttp, matplotlib, aiofiles

---

## File Map

| File | Responsibility |
|---|---|
| `config.py` | Load `.env` + `config.json`, provide typed config object |
| `core/notifier.py` | Send messages to Telegram user |
| `core/project_registry.py` | CRUD projects, scan for git repos, persist to JSON |
| `core/session_manager.py` | Launch/kill claude processes, parse output, track sessions |
| `core/limit_tracker.py` | Poll usage API, fire threshold callbacks |
| `analytics/collector.py` | Append usage data to monthly CSV files |
| `analytics/charts.py` | Generate matplotlib PNG charts from CSV data |
| `analytics/handlers.py` | Telegram command handlers for `/usage*` commands |
| `handlers/projects.py` | Telegram UI for project management |
| `handlers/sessions.py` | Telegram UI for session wizard and active sessions list |
| `handlers/settings.py` | Telegram UI for viewing settings |
| `bot.py` | Entry point, wire components, register handlers, start polling |
| `tests/test_config.py` | Tests for config loading |
| `tests/test_project_registry.py` | Tests for project CRUD and scanning |
| `tests/test_session_manager.py` | Tests for URL parsing, session lifecycle |
| `tests/test_limit_tracker.py` | Tests for threshold logic, API parsing |
| `tests/test_collector.py` | Tests for CSV writing |
| `tests/test_charts.py` | Tests for chart data loading |

---

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `config.example.json`
- Create: `core/__init__.py`
- Create: `handlers/__init__.py`
- Create: `analytics/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
python-telegram-bot==21.10
aiohttp==3.11.11
aiofiles==24.1.0
matplotlib==3.10.0
python-dotenv==1.0.1
pytest==8.3.4
pytest-asyncio==0.25.0
```

- [ ] **Step 2: Create `.gitignore`**

```
.env
config.json
data/
logs/
__pycache__/
venv/
*.pyc
.pytest_cache/
```

- [ ] **Step 3: Create `.env.example`**

```
# Telegram bot token from @BotFather
TELEGRAM_BOT_TOKEN=
# Your Telegram user ID (get it from @userinfobot)
TELEGRAM_USER_ID=
```

- [ ] **Step 4: Create `config.example.json`**

```json
{
  "projects_dir": "E:\\",
  "poll_interval_sec": 60,
  "thresholds": [70, 85, 95],
  "log_level": "INFO"
}
```

- [ ] **Step 5: Create empty `__init__.py` files**

Create empty files:
- `core/__init__.py`
- `handlers/__init__.py`
- `analytics/__init__.py`
- `tests/__init__.py`

- [ ] **Step 6: Create data directories**

```bash
mkdir -p data/usage logs
```

- [ ] **Step 7: Initialize git repo and commit**

```bash
git init
git add requirements.txt .gitignore .env.example config.example.json core/__init__.py handlers/__init__.py analytics/__init__.py tests/__init__.py
git commit -m "chore: project scaffolding"
```

---

### Task 2: Config Module

**Files:**
- Create: `config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for config**

```python
# tests/test_config.py
import json
import os
import pytest
from unittest.mock import patch


def test_load_config_from_file(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "projects_dir": "D:\\projects",
        "poll_interval_sec": 30,
        "thresholds": [60, 80, 90],
        "log_level": "DEBUG"
    }))

    env = {
        "TELEGRAM_BOT_TOKEN": "test-token-123",
        "TELEGRAM_USER_ID": "999",
    }

    with patch.dict(os.environ, env, clear=False):
        from config import load_config
        cfg = load_config(config_path=str(config_path))

    assert cfg.telegram_bot_token == "test-token-123"
    assert cfg.telegram_user_id == 999
    assert cfg.projects_dir == "D:\\projects"
    assert cfg.poll_interval_sec == 30
    assert cfg.thresholds == [60, 80, 90]
    assert cfg.log_level == "DEBUG"


def test_load_config_defaults(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")

    env = {
        "TELEGRAM_BOT_TOKEN": "tok",
        "TELEGRAM_USER_ID": "1",
    }

    with patch.dict(os.environ, env, clear=False):
        from config import load_config
        cfg = load_config(config_path=str(config_path))

    assert cfg.poll_interval_sec == 60
    assert cfg.thresholds == [70, 85, 95]
    assert cfg.log_level == "INFO"


def test_load_config_missing_token(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")

    env = {"TELEGRAM_USER_ID": "1"}
    with patch.dict(os.environ, env, clear=False):
        # Remove TELEGRAM_BOT_TOKEN if present
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        from config import load_config
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            load_config(config_path=str(config_path))


def test_claude_credentials_path():
    from config import get_claude_credentials_path
    path = get_claude_credentials_path()
    assert ".claude" in path
    assert path.endswith(".credentials.json")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 3: Implement config.py**

```python
# config.py
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    telegram_bot_token: str
    telegram_user_id: int
    projects_dir: str = ""
    poll_interval_sec: int = 60
    thresholds: list[int] = field(default_factory=lambda: [70, 85, 95])
    log_level: str = "INFO"


def load_config(config_path: str = "config.json") -> Config:
    load_dotenv()

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

    user_id_str = os.environ.get("TELEGRAM_USER_ID")
    if not user_id_str:
        raise ValueError("TELEGRAM_USER_ID is not set in .env")

    file_config = {}
    if Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            file_config = json.load(f)

    return Config(
        telegram_bot_token=bot_token,
        telegram_user_id=int(user_id_str),
        projects_dir=file_config.get("projects_dir", ""),
        poll_interval_sec=file_config.get("poll_interval_sec", 60),
        thresholds=file_config.get("thresholds", [70, 85, 95]),
        log_level=file_config.get("log_level", "INFO"),
    )


def get_claude_credentials_path() -> str:
    home = Path.home()
    return str(home / ".claude" / ".credentials.json")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: config module with .env and config.json loading"
```

---

### Task 3: Notifier

**Files:**
- Create: `core/notifier.py`
- Create: `tests/test_notifier.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_notifier.py
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from core.notifier import Notifier


@pytest.fixture
def bot():
    b = AsyncMock()
    b.send_message = AsyncMock()
    return b


@pytest.fixture
def notifier(bot):
    return Notifier(bot=bot, chat_id=123)


@pytest.mark.asyncio
async def test_send_message(notifier, bot):
    await notifier.send("Hello test")
    bot.send_message.assert_called_once_with(
        chat_id=123, text="Hello test", parse_mode="HTML"
    )


@pytest.mark.asyncio
async def test_session_started_remote(notifier, bot):
    await notifier.session_started(
        project="my-app",
        mode="remote",
        url="https://claude.ai/code/session_abc123"
    )
    call_text = bot.send_message.call_args[1]["text"]
    assert "my-app" in call_text
    assert "https://claude.ai/code/session_abc123" in call_text


@pytest.mark.asyncio
async def test_session_started_normal(notifier, bot):
    await notifier.session_started(project="my-app", mode="normal")
    call_text = bot.send_message.call_args[1]["text"]
    assert "my-app" in call_text


@pytest.mark.asyncio
async def test_session_finished(notifier, bot):
    await notifier.session_finished(project="my-app", duration_min=12)
    call_text = bot.send_message.call_args[1]["text"]
    assert "my-app" in call_text
    assert "12" in call_text


@pytest.mark.asyncio
async def test_session_error(notifier, bot):
    await notifier.session_error(project="my-app", error="segfault")
    call_text = bot.send_message.call_args[1]["text"]
    assert "my-app" in call_text
    assert "segfault" in call_text


@pytest.mark.asyncio
async def test_limit_warning(notifier, bot):
    await notifier.limit_warning(
        period="5h", percent=70, reset_minutes=42
    )
    call_text = bot.send_message.call_args[1]["text"]
    assert "70" in call_text
    assert "42" in call_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_notifier.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.notifier'`

- [ ] **Step 3: Implement notifier**

```python
# core/notifier.py
import logging

from telegram import Bot

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot: Bot, chat_id: int):
        self._bot = bot
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        try:
            await self._bot.send_message(
                chat_id=self._chat_id, text=text, parse_mode="HTML"
            )
        except Exception:
            logger.exception("Failed to send notification")

    async def session_started(
        self, project: str, mode: str, url: str | None = None
    ) -> None:
        if mode == "remote" and url:
            text = f"🚀 <b>{project}</b>: сессия запущена\n📎 {url}"
        else:
            text = f"🚀 <b>{project}</b>: задача запущена"
        await self.send(text)

    async def session_finished(self, project: str, duration_min: int) -> None:
        await self.send(
            f"✅ <b>{project}</b>: завершилась ({duration_min} мин)"
        )

    async def session_error(self, project: str, error: str) -> None:
        await self.send(f"❌ <b>{project}</b>: ошибка\n<pre>{error}</pre>")

    async def rate_limit(self, project: str) -> None:
        await self.send(f"⏸️ <b>{project}</b>: rate limit, ожидание")

    async def limit_warning(
        self, period: str, percent: int, reset_minutes: int
    ) -> None:
        icons = {70: "⚠️", 85: "⛔", 95: "🔴"}
        icon = icons.get(percent, "⚠️")
        await self.send(
            f"{icon} {period} лимит {percent}% — reset через {reset_minutes} мин"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_notifier.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/notifier.py tests/test_notifier.py
git commit -m "feat: notifier for Telegram notifications"
```

---

### Task 4: Project Registry

**Files:**
- Create: `core/project_registry.py`
- Create: `tests/test_project_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_project_registry.py
import json
import pytest
from pathlib import Path

from core.project_registry import ProjectRegistry


@pytest.fixture
def registry(tmp_path):
    data_file = tmp_path / "projects.json"
    return ProjectRegistry(data_file=str(data_file))


@pytest.fixture
def fake_projects_dir(tmp_path):
    """Create a directory with some git repos and some non-git dirs."""
    for name in ["repo-a", "repo-b", "repo-c"]:
        d = tmp_path / name
        d.mkdir()
        (d / ".git").mkdir()
    # Non-git directory
    (tmp_path / "not-a-repo").mkdir()
    return tmp_path


def test_scan_finds_git_repos(registry, fake_projects_dir):
    found = registry.scan(str(fake_projects_dir))
    names = [r["name"] for r in found]
    assert sorted(names) == ["repo-a", "repo-b", "repo-c"]


def test_scan_ignores_non_git(registry, fake_projects_dir):
    found = registry.scan(str(fake_projects_dir))
    names = [r["name"] for r in found]
    assert "not-a-repo" not in names


def test_add_project(registry, fake_projects_dir):
    registry.add("repo-a", str(fake_projects_dir / "repo-a"))
    projects = registry.list()
    assert len(projects) == 1
    assert projects[0]["name"] == "repo-a"
    assert projects[0]["path"] == str(fake_projects_dir / "repo-a")
    assert "added_at" in projects[0]


def test_add_duplicate_raises(registry, fake_projects_dir):
    path = str(fake_projects_dir / "repo-a")
    registry.add("repo-a", path)
    with pytest.raises(ValueError, match="already registered"):
        registry.add("repo-a", path)


def test_remove_project(registry, fake_projects_dir):
    registry.add("repo-a", str(fake_projects_dir / "repo-a"))
    registry.remove("repo-a")
    assert registry.list() == []


def test_remove_nonexistent_raises(registry):
    with pytest.raises(ValueError, match="not found"):
        registry.remove("nope")


def test_persistence(tmp_path, fake_projects_dir):
    data_file = tmp_path / "projects.json"
    reg1 = ProjectRegistry(data_file=str(data_file))
    reg1.add("repo-a", str(fake_projects_dir / "repo-a"))

    reg2 = ProjectRegistry(data_file=str(data_file))
    assert len(reg2.list()) == 1
    assert reg2.list()[0]["name"] == "repo-a"


def test_get_project(registry, fake_projects_dir):
    registry.add("repo-a", str(fake_projects_dir / "repo-a"))
    project = registry.get("repo-a")
    assert project["name"] == "repo-a"


def test_get_nonexistent_returns_none(registry):
    assert registry.get("nope") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_project_registry.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement project registry**

```python
# core/project_registry.py
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class ProjectRegistry:
    def __init__(self, data_file: str = "data/projects.json"):
        self._data_file = Path(data_file)
        self._projects: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self._data_file.exists():
            with open(self._data_file, "r", encoding="utf-8") as f:
                self._projects = json.load(f)

    def _save(self) -> None:
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._data_file, "w", encoding="utf-8") as f:
            json.dump(self._projects, f, ensure_ascii=False, indent=2)

    def scan(self, directory: str) -> list[dict]:
        results = []
        base = Path(directory)
        if not base.is_dir():
            return results
        for child in sorted(base.iterdir()):
            if child.is_dir() and (child / ".git").exists():
                results.append({"name": child.name, "path": str(child)})
        return results

    def add(self, name: str, path: str) -> dict:
        if any(p["name"] == name for p in self._projects):
            raise ValueError(f"Project '{name}' already registered")
        project = {
            "name": name,
            "path": path,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self._projects.append(project)
        self._save()
        return project

    def remove(self, name: str) -> None:
        idx = next(
            (i for i, p in enumerate(self._projects) if p["name"] == name),
            None,
        )
        if idx is None:
            raise ValueError(f"Project '{name}' not found")
        self._projects.pop(idx)
        self._save()

    def list(self) -> list[dict]:
        return list(self._projects)

    def get(self, name: str) -> dict | None:
        return next(
            (p for p in self._projects if p["name"] == name), None
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_project_registry.py -v`
Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/project_registry.py tests/test_project_registry.py
git commit -m "feat: project registry with scan, CRUD, and JSON persistence"
```

---

### Task 5: Session Manager

**Files:**
- Create: `core/session_manager.py`
- Create: `tests/test_session_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_session_manager.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from core.session_manager import SessionManager, SessionInfo, parse_remote_url


def test_parse_remote_url_from_output():
    output = (
        "some banner text\n"
        "/remote-control is active. Code in CLI or at "
        "https://claude.ai/code/session_01W3hMJKdHto461D9Yk4hY1w\n"
        "more text"
    )
    url = parse_remote_url(output)
    assert url == "https://claude.ai/code/session_01W3hMJKdHto461D9Yk4hY1w"


def test_parse_remote_url_no_match():
    assert parse_remote_url("no url here") is None


def test_parse_remote_url_standalone_url():
    output = "https://claude.ai/code/session_abc123"
    url = parse_remote_url(output)
    assert url == "https://claude.ai/code/session_abc123"


@pytest.fixture
def notifier():
    n = AsyncMock()
    n.session_started = AsyncMock()
    n.session_finished = AsyncMock()
    n.session_error = AsyncMock()
    return n


@pytest.fixture
def manager(notifier):
    return SessionManager(notifier=notifier)


def test_no_active_sessions(manager):
    assert manager.list_sessions() == []


def test_session_info_duration():
    info = SessionInfo(
        session_id="test-1",
        project_name="proj",
        mode="remote",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        process=MagicMock(),
    )
    # Duration depends on current time; just check it returns an int
    assert isinstance(info.duration_minutes(), int)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_session_manager.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement session manager**

```python
# core/session_manager.py
import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.notifier import Notifier

logger = logging.getLogger(__name__)

_REMOTE_URL_RE = re.compile(r"(https://claude\.ai/code/session_\S+)")


def parse_remote_url(text: str) -> str | None:
    match = _REMOTE_URL_RE.search(text)
    return match.group(1) if match else None


@dataclass
class SessionInfo:
    session_id: str
    project_name: str
    mode: str  # "remote" or "normal"
    started_at: datetime
    process: asyncio.subprocess.Process
    url: str | None = None

    def duration_minutes(self) -> int:
        delta = datetime.now(timezone.utc) - self.started_at
        return int(delta.total_seconds() / 60)


class SessionManager:
    def __init__(self, notifier: Notifier):
        self._notifier = notifier
        self._sessions: dict[str, SessionInfo] = {}

    def list_sessions(self) -> list[SessionInfo]:
        return list(self._sessions.values())

    def get_session(self, session_id: str) -> SessionInfo | None:
        return self._sessions.get(session_id)

    async def start_remote(self, project_name: str, project_path: str, prompt: str = "") -> SessionInfo:
        cmd = ["claude", "--remote-control"]
        if prompt:
            cmd.append(prompt)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_path,
        )

        session_id = str(uuid.uuid4())[:8]
        info = SessionInfo(
            session_id=session_id,
            project_name=project_name,
            mode="remote",
            started_at=datetime.now(timezone.utc),
            process=process,
        )
        self._sessions[session_id] = info

        # Read stdout in background to find URL
        asyncio.create_task(self._read_remote_output(info))
        # Monitor process lifecycle
        asyncio.create_task(self._monitor_process(info))

        return info

    async def start_normal(self, project_name: str, project_path: str, prompt: str) -> SessionInfo:
        cmd = ["claude", "-p", "--output-format", "json", prompt]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_path,
        )

        session_id = str(uuid.uuid4())[:8]
        info = SessionInfo(
            session_id=session_id,
            project_name=project_name,
            mode="normal",
            started_at=datetime.now(timezone.utc),
            process=process,
        )
        self._sessions[session_id] = info

        await self._notifier.session_started(project=project_name, mode="normal")
        # Monitor process lifecycle
        asyncio.create_task(self._monitor_process(info))

        return info

    async def kill_session(self, session_id: str) -> bool:
        info = self._sessions.get(session_id)
        if not info:
            return False

        info.process.terminate()
        try:
            await asyncio.wait_for(info.process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            info.process.kill()
            await info.process.wait()

        self._sessions.pop(session_id, None)
        return True

    async def _read_remote_output(self, info: SessionInfo) -> None:
        collected = ""
        try:
            while True:
                chunk = await info.process.stdout.read(4096)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                collected += text
                url = parse_remote_url(collected)
                if url:
                    info.url = url
                    await self._notifier.session_started(
                        project=info.project_name, mode="remote", url=url
                    )
                    break
            # Continue draining stdout
            while True:
                chunk = await info.process.stdout.read(4096)
                if not chunk:
                    break
        except Exception:
            logger.exception("Error reading remote output for %s", info.project_name)

    async def _monitor_process(self, info: SessionInfo) -> None:
        returncode = await info.process.wait()
        duration = info.duration_minutes()
        self._sessions.pop(info.session_id, None)

        if returncode == 0:
            await self._notifier.session_finished(
                project=info.project_name, duration_min=duration
            )
        else:
            stderr_bytes = await info.process.stderr.read() if info.process.stderr else b""
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")[-500:]
            await self._notifier.session_error(
                project=info.project_name, error=stderr_text or f"exit code {returncode}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_session_manager.py -v`
Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/session_manager.py tests/test_session_manager.py
git commit -m "feat: session manager with remote-control and normal modes"
```

---

### Task 6: Limit Tracker

**Files:**
- Create: `core/limit_tracker.py`
- Create: `tests/test_limit_tracker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_limit_tracker.py
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from core.limit_tracker import LimitTracker, UsageData, parse_usage_response


SAMPLE_RESPONSE = {
    "five_hour": {"utilization": 0.72, "resets_at": "2026-04-10T18:00:00Z"},
    "seven_day": {"utilization": 0.12, "resets_at": "2026-04-14T00:00:00Z"},
    "seven_day_sonnet": {"utilization": 0.08, "resets_at": "2026-04-14T00:00:00Z"},
    "extra_usage": {
        "is_enabled": True,
        "monthly_limit": 10000,
        "used_credits": 500,
        "utilization": 0.05
    }
}


def test_parse_usage_response():
    data = parse_usage_response(SAMPLE_RESPONSE)
    assert data.five_hour_util == 0.72
    assert data.seven_day_util == 0.12
    assert data.seven_day_sonnet_util == 0.08
    assert data.five_hour_resets_at == "2026-04-10T18:00:00Z"
    assert data.seven_day_resets_at == "2026-04-14T00:00:00Z"


def test_parse_usage_response_missing_fields():
    data = parse_usage_response({"five_hour": {"utilization": 0.5, "resets_at": "x"}})
    assert data.five_hour_util == 0.5
    assert data.seven_day_util == 0.0
    assert data.seven_day_sonnet_util == 0.0


@pytest.fixture
def notifier():
    n = AsyncMock()
    n.limit_warning = AsyncMock()
    return n


def test_threshold_triggers(notifier):
    tracker = LimitTracker(
        notifier=notifier,
        thresholds=[70, 85, 95],
        poll_interval_sec=60,
        credentials_path="dummy",
    )
    # 72% should trigger 70% threshold
    triggered = tracker._check_thresholds("5h", 0.72)
    assert 70 in triggered
    assert 85 not in triggered


def test_threshold_fires_once(notifier):
    tracker = LimitTracker(
        notifier=notifier,
        thresholds=[70, 85, 95],
        poll_interval_sec=60,
        credentials_path="dummy",
    )
    triggered1 = tracker._check_thresholds("5h", 0.72)
    triggered2 = tracker._check_thresholds("5h", 0.74)
    assert 70 in triggered1
    assert 70 not in triggered2  # Already fired


def test_threshold_resets_when_utilization_drops(notifier):
    tracker = LimitTracker(
        notifier=notifier,
        thresholds=[70, 85, 95],
        poll_interval_sec=60,
        credentials_path="dummy",
    )
    tracker._check_thresholds("5h", 0.72)
    # Utilization drops below 70% (reset happened)
    tracker._check_thresholds("5h", 0.10)
    # Should fire again when crossing 70%
    triggered = tracker._check_thresholds("5h", 0.75)
    assert 70 in triggered


def test_multiple_thresholds_at_once(notifier):
    tracker = LimitTracker(
        notifier=notifier,
        thresholds=[70, 85, 95],
        poll_interval_sec=60,
        credentials_path="dummy",
    )
    triggered = tracker._check_thresholds("5h", 0.96)
    assert 70 in triggered
    assert 85 in triggered
    assert 95 in triggered
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_limit_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement limit tracker**

```python
# core/limit_tracker.py
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import aiohttp

from core.notifier import Notifier

logger = logging.getLogger(__name__)

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"


@dataclass
class UsageData:
    five_hour_util: float = 0.0
    five_hour_resets_at: str = ""
    seven_day_util: float = 0.0
    seven_day_resets_at: str = ""
    seven_day_sonnet_util: float = 0.0
    timestamp: str = ""


def parse_usage_response(data: dict) -> UsageData:
    five_hour = data.get("five_hour", {})
    seven_day = data.get("seven_day", {})
    seven_day_sonnet = data.get("seven_day_sonnet", {})
    return UsageData(
        five_hour_util=five_hour.get("utilization", 0.0),
        five_hour_resets_at=five_hour.get("resets_at", ""),
        seven_day_util=seven_day.get("utilization", 0.0),
        seven_day_resets_at=seven_day.get("resets_at", ""),
        seven_day_sonnet_util=seven_day_sonnet.get("utilization", 0.0),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


class LimitTracker:
    def __init__(
        self,
        notifier: Notifier,
        thresholds: list[int],
        poll_interval_sec: int,
        credentials_path: str,
        on_usage: Callable[[UsageData], None] | None = None,
    ):
        self._notifier = notifier
        self._thresholds = sorted(thresholds)
        self._poll_interval = poll_interval_sec
        self._credentials_path = credentials_path
        self._on_usage = on_usage
        self._fired: dict[str, set[int]] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self.latest: UsageData | None = None

    def _get_token(self) -> str | None:
        try:
            with open(self._credentials_path, "r", encoding="utf-8") as f:
                creds = json.load(f)
            return creds.get("claudeAiOauth", {}).get("accessToken")
        except Exception:
            logger.exception("Failed to read credentials")
            return None

    def _check_thresholds(self, period: str, utilization: float) -> set[int]:
        percent = utilization * 100
        if period not in self._fired:
            self._fired[period] = set()

        # Reset fired thresholds if utilization dropped below them
        to_reset = {t for t in self._fired[period] if percent < t}
        self._fired[period] -= to_reset

        triggered = set()
        for threshold in self._thresholds:
            if percent >= threshold and threshold not in self._fired[period]:
                triggered.add(threshold)
                self._fired[period].add(threshold)

        return triggered

    async def _poll_once(self) -> UsageData | None:
        token = self._get_token()
        if not token:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
                async with session.get(USAGE_URL, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning("Usage API returned %d", resp.status)
                        return None
                    data = await resp.json()
                    return parse_usage_response(data)
        except Exception:
            logger.exception("Failed to poll usage API")
            return None

    async def _notify_thresholds(self, usage: UsageData) -> None:
        for period, util, resets_at in [
            ("5h", usage.five_hour_util, usage.five_hour_resets_at),
            ("7d", usage.seven_day_util, usage.seven_day_resets_at),
        ]:
            triggered = self._check_thresholds(period, util)
            for threshold in sorted(triggered):
                reset_min = 0
                if resets_at:
                    try:
                        reset_dt = datetime.fromisoformat(resets_at)
                        delta = reset_dt - datetime.now(timezone.utc)
                        reset_min = max(0, int(delta.total_seconds() / 60))
                    except ValueError:
                        pass
                await self._notifier.limit_warning(
                    period=period, percent=threshold, reset_minutes=reset_min
                )

    async def _poll_loop(self) -> None:
        while self._running:
            usage = await self._poll_once()
            if usage:
                self.latest = usage
                await self._notify_thresholds(usage)
                if self._on_usage:
                    self._on_usage(usage)
            await asyncio.sleep(self._poll_interval)

    def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_limit_tracker.py -v`
Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/limit_tracker.py tests/test_limit_tracker.py
git commit -m "feat: limit tracker with usage API polling and threshold alerts"
```

---

### Task 7: Analytics Collector

**Files:**
- Create: `analytics/collector.py`
- Create: `tests/test_collector.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_collector.py
import csv
import pytest
from pathlib import Path
from datetime import datetime

from analytics.collector import UsageCollector
from core.limit_tracker import UsageData


@pytest.fixture
def collector(tmp_path):
    return UsageCollector(data_dir=str(tmp_path))


def _make_usage(five=0.35, seven=0.12, sonnet=0.08, ts="2026-04-10T14:30:00+00:00"):
    return UsageData(
        five_hour_util=five,
        seven_day_util=seven,
        seven_day_sonnet_util=sonnet,
        timestamp=ts,
    )


def test_record_creates_csv(collector, tmp_path):
    usage = _make_usage()
    collector.record(usage)
    csv_file = tmp_path / "2026-04.csv"
    assert csv_file.exists()


def test_record_writes_header_and_row(collector, tmp_path):
    usage = _make_usage()
    collector.record(usage)
    csv_file = tmp_path / "2026-04.csv"
    lines = csv_file.read_text().strip().split("\n")
    assert len(lines) == 2  # header + 1 row
    assert lines[0] == "timestamp,five_hour_util,seven_day_util,seven_day_sonnet_util"
    parts = lines[1].split(",")
    assert parts[0] == "2026-04-10T14:30:00+00:00"
    assert float(parts[1]) == 0.35


def test_record_appends_to_existing(collector, tmp_path):
    collector.record(_make_usage(five=0.1, ts="2026-04-10T14:00:00+00:00"))
    collector.record(_make_usage(five=0.2, ts="2026-04-10T14:30:00+00:00"))
    csv_file = tmp_path / "2026-04.csv"
    lines = csv_file.read_text().strip().split("\n")
    assert len(lines) == 3  # header + 2 rows


def test_different_months_different_files(collector, tmp_path):
    collector.record(_make_usage(ts="2026-04-10T14:00:00+00:00"))
    collector.record(_make_usage(ts="2026-05-01T10:00:00+00:00"))
    assert (tmp_path / "2026-04.csv").exists()
    assert (tmp_path / "2026-05.csv").exists()


def test_load_data(collector, tmp_path):
    collector.record(_make_usage(five=0.1, ts="2026-04-10T14:00:00+00:00"))
    collector.record(_make_usage(five=0.2, ts="2026-04-10T15:00:00+00:00"))
    rows = collector.load("2026-04")
    assert len(rows) == 2
    assert rows[0]["five_hour_util"] == "0.1"
    assert rows[1]["five_hour_util"] == "0.2"


def test_load_nonexistent_returns_empty(collector):
    assert collector.load("2099-01") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_collector.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement collector**

```python
# analytics/collector.py
import csv
import logging
from datetime import datetime
from pathlib import Path

from core.limit_tracker import UsageData

logger = logging.getLogger(__name__)

FIELDNAMES = ["timestamp", "five_hour_util", "seven_day_util", "seven_day_sonnet_util"]


class UsageCollector:
    def __init__(self, data_dir: str = "data/usage"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _csv_path(self, timestamp: str) -> Path:
        dt = datetime.fromisoformat(timestamp)
        filename = dt.strftime("%Y-%m") + ".csv"
        return self._data_dir / filename

    def record(self, usage: UsageData) -> None:
        csv_path = self._csv_path(usage.timestamp)
        file_exists = csv_path.exists()

        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                "timestamp": usage.timestamp,
                "five_hour_util": usage.five_hour_util,
                "seven_day_util": usage.seven_day_util,
                "seven_day_sonnet_util": usage.seven_day_sonnet_util,
            })

    def load(self, year_month: str) -> list[dict]:
        csv_path = self._data_dir / f"{year_month}.csv"
        if not csv_path.exists():
            return []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_collector.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add analytics/collector.py tests/test_collector.py
git commit -m "feat: usage collector writing to monthly CSV files"
```

---

### Task 8: Analytics Charts

**Files:**
- Create: `analytics/charts.py`
- Create: `tests/test_charts.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_charts.py
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from analytics.collector import UsageCollector
from analytics.charts import UsageCharts


@pytest.fixture
def collector(tmp_path):
    c = UsageCollector(data_dir=str(tmp_path))
    from core.limit_tracker import UsageData
    # Add 48 hours of data (every 30 min)
    for day in [10, 11]:
        for hour in range(24):
            for minute in [0, 30]:
                c.record(UsageData(
                    five_hour_util=0.3 + (hour / 100),
                    seven_day_util=0.1,
                    seven_day_sonnet_util=0.05,
                    timestamp=f"2026-04-{day:02d}T{hour:02d}:{minute:02d}:00+00:00",
                ))
    return c


@pytest.fixture
def charts(collector, tmp_path):
    return UsageCharts(collector=collector, output_dir=str(tmp_path / "charts"))


def test_generate_day_chart(charts, tmp_path):
    path = charts.generate_day("2026-04-10")
    assert Path(path).exists()
    assert path.endswith(".png")


def test_generate_week_chart(charts, tmp_path):
    path = charts.generate_week("2026-04-10")
    assert Path(path).exists()
    assert path.endswith(".png")


def test_generate_heatmap(charts, tmp_path):
    path = charts.generate_heatmap("2026-04")
    assert Path(path).exists()
    assert path.endswith(".png")


def test_generate_day_no_data(charts):
    path = charts.generate_day("2099-01-01")
    assert path is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_charts.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement charts**

```python
# analytics/charts.py
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from analytics.collector import UsageCollector

logger = logging.getLogger(__name__)


class UsageCharts:
    def __init__(self, collector: UsageCollector, output_dir: str = "data/charts"):
        self._collector = collector
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def _filter_rows(self, rows: list[dict], start: datetime, end: datetime) -> list[dict]:
        result = []
        for row in rows:
            dt = datetime.fromisoformat(row["timestamp"])
            if start <= dt < end:
                result.append(row)
        return result

    def generate_day(self, date_str: str) -> str | None:
        """Generate chart for a single day. date_str format: YYYY-MM-DD"""
        year_month = date_str[:7]
        rows = self._collector.load(year_month)
        day_start = datetime.fromisoformat(f"{date_str}T00:00:00+00:00")
        day_end = day_start + timedelta(days=1)
        day_rows = self._filter_rows(rows, day_start, day_end)

        if not day_rows:
            return None

        times = [datetime.fromisoformat(r["timestamp"]) for r in day_rows]
        five_h = [float(r["five_hour_util"]) * 100 for r in day_rows]
        seven_d = [float(r["seven_day_util"]) * 100 for r in day_rows]

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(times, five_h, label="5h limit", linewidth=2)
        ax.plot(times, seven_d, label="7d limit", linewidth=2)
        ax.set_ylabel("Usage %")
        ax.set_title(f"Usage — {date_str}")
        ax.legend()
        ax.set_ylim(0, 100)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        out_path = str(self._output_dir / f"day_{date_str}.png")
        fig.savefig(out_path, dpi=100)
        plt.close(fig)
        return out_path

    def generate_week(self, date_str: str) -> str | None:
        """Generate chart for 7 days ending on date_str."""
        end = datetime.fromisoformat(f"{date_str}T23:59:59+00:00")
        start = end - timedelta(days=7)

        all_rows = []
        # May span two months
        for month_offset in range(2):
            dt = start + timedelta(days=month_offset * 28)
            ym = dt.strftime("%Y-%m")
            all_rows.extend(self._collector.load(ym))

        week_rows = self._filter_rows(all_rows, start, end + timedelta(seconds=1))
        if not week_rows:
            return None

        times = [datetime.fromisoformat(r["timestamp"]) for r in week_rows]
        five_h = [float(r["five_hour_util"]) * 100 for r in week_rows]
        seven_d = [float(r["seven_day_util"]) * 100 for r in week_rows]

        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(times, five_h, label="5h limit", linewidth=1.5)
        ax.plot(times, seven_d, label="7d limit", linewidth=1.5)
        ax.set_ylabel("Usage %")
        ax.set_title(f"Usage — week ending {date_str}")
        ax.legend()
        ax.set_ylim(0, 100)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        out_path = str(self._output_dir / f"week_{date_str}.png")
        fig.savefig(out_path, dpi=100)
        plt.close(fig)
        return out_path

    def generate_heatmap(self, year_month: str) -> str | None:
        """Generate heatmap: hours (x) vs weekdays (y) for five_hour_util."""
        rows = self._collector.load(year_month)
        if not rows:
            return None

        # Aggregate: weekday x hour -> list of values
        grid = defaultdict(list)
        for row in rows:
            dt = datetime.fromisoformat(row["timestamp"])
            grid[(dt.weekday(), dt.hour)].append(float(row["five_hour_util"]) * 100)

        # Build 7x24 matrix (Mon=0 .. Sun=6)
        import numpy as np
        matrix = np.full((7, 24), float("nan"))
        for (wd, h), vals in grid.items():
            matrix[wd][h] = sum(vals) / len(vals)

        fig, ax = plt.subplots(figsize=(12, 4))
        im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=100)
        ax.set_yticks(range(7))
        ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        ax.set_xticks(range(24))
        ax.set_xticklabels([f"{h:02d}" for h in range(24)])
        ax.set_xlabel("Hour (UTC)")
        ax.set_title(f"5h Usage Heatmap — {year_month}")
        fig.colorbar(im, ax=ax, label="Usage %")
        fig.tight_layout()

        out_path = str(self._output_dir / f"heatmap_{year_month}.png")
        fig.savefig(out_path, dpi=100)
        plt.close(fig)
        return out_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_charts.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add analytics/charts.py tests/test_charts.py
git commit -m "feat: usage charts — day, week, and heatmap generation"
```

---

### Task 9: Auth Middleware

**Files:**
- Create: `handlers/auth.py`

This is a simple decorator/check used by all handlers to verify the Telegram user is authorized.

- [ ] **Step 1: Implement auth check**

```python
# handlers/auth.py
import functools
import logging
from typing import Callable

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def authorized(user_id: int) -> Callable:
    """Decorator that silently ignores updates from unauthorized users."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            effective_user = update.effective_user
            if not effective_user or effective_user.id != user_id:
                logger.warning("Unauthorized access from user %s", effective_user)
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator
```

- [ ] **Step 2: Commit**

```bash
git add handlers/auth.py
git commit -m "feat: auth middleware for Telegram handler authorization"
```

---

### Task 10: Telegram Handlers — Projects

**Files:**
- Create: `handlers/projects.py`

- [ ] **Step 1: Implement project handlers**

```python
# handlers/projects.py
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)

from core.project_registry import ProjectRegistry

logger = logging.getLogger(__name__)

# Callback data prefixes
CB_PROJECTS = "projects"
CB_PROJECT_ADD = "proj_add"
CB_PROJECT_SCAN = "proj_scan:"
CB_PROJECT_REMOVE = "proj_rm"
CB_PROJECT_RM_CONFIRM = "proj_rm_confirm:"
CB_BACK_MAIN = "main_menu"


def create_project_handlers(registry: ProjectRegistry, auth_check):
    """Create and return handlers for project management."""

    @auth_check
    async def show_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query:
            await query.answer()

        projects = registry.list()
        if not projects:
            text = "📂 Нет зарегистрированных проектов"
        else:
            lines = ["📂 <b>Проекты:</b>\n"]
            for p in projects:
                lines.append(f"  • <b>{p['name']}</b>\n    <code>{p['path']}</code>")
            text = "\n".join(lines)

        keyboard = [
            [InlineKeyboardButton("➕ Добавить", callback_data=CB_PROJECT_ADD)],
        ]
        if projects:
            keyboard.append(
                [InlineKeyboardButton("❌ Удалить", callback_data=CB_PROJECT_REMOVE)]
            )
        keyboard.append(
            [InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)]
        )

        if query:
            await query.edit_message_text(
                text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
            )

    @auth_check
    async def scan_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        projects_dir = context.bot_data.get("config").projects_dir
        if not projects_dir:
            await query.edit_message_text("⚙️ projects_dir не задан в config.json")
            return

        found = registry.scan(projects_dir)
        registered_names = {p["name"] for p in registry.list()}
        new_repos = [r for r in found if r["name"] not in registered_names]

        if not new_repos:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=CB_PROJECTS)]]
            await query.edit_message_text(
                "Новых git-репозиториев не найдено",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return

        keyboard = [
            [InlineKeyboardButton(r["name"], callback_data=f"{CB_PROJECT_SCAN}{r['name']}|{r['path']}")]
            for r in new_repos
        ]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=CB_PROJECTS)])

        await query.edit_message_text(
            f"Найдено {len(new_repos)} репозиториев:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    @auth_check
    async def add_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data.replace(CB_PROJECT_SCAN, "")
        name, path = data.split("|", 1)

        try:
            registry.add(name, path)
            text = f"✅ Проект <b>{name}</b> зарегистрирован\n<code>{path}</code>"
        except ValueError as e:
            text = f"⚠️ {e}"

        keyboard = [[InlineKeyboardButton("🔙 К проектам", callback_data=CB_PROJECTS)]]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )

    @auth_check
    async def show_remove_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        projects = registry.list()
        keyboard = [
            [InlineKeyboardButton(f"❌ {p['name']}", callback_data=f"{CB_PROJECT_RM_CONFIRM}{p['name']}")]
            for p in projects
        ]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=CB_PROJECTS)])

        await query.edit_message_text(
            "Выбери проект для удаления:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    @auth_check
    async def remove_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        name = query.data.replace(CB_PROJECT_RM_CONFIRM, "")

        try:
            registry.remove(name)
            text = f"✅ Проект <b>{name}</b> удалён"
        except ValueError as e:
            text = f"⚠️ {e}"

        keyboard = [[InlineKeyboardButton("🔙 К проектам", callback_data=CB_PROJECTS)]]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )

    return [
        CallbackQueryHandler(show_projects, pattern=f"^{CB_PROJECTS}$"),
        CallbackQueryHandler(scan_projects, pattern=f"^{CB_PROJECT_ADD}$"),
        CallbackQueryHandler(add_project, pattern=f"^{CB_PROJECT_SCAN}"),
        CallbackQueryHandler(show_remove_list, pattern=f"^{CB_PROJECT_REMOVE}$"),
        CallbackQueryHandler(remove_project, pattern=f"^{CB_PROJECT_RM_CONFIRM}"),
    ]
```

- [ ] **Step 2: Commit**

```bash
git add handlers/projects.py
git commit -m "feat: Telegram handlers for project management"
```

---

### Task 11: Telegram Handlers — Sessions

**Files:**
- Create: `handlers/sessions.py`

- [ ] **Step 1: Implement session handlers**

```python
# handlers/sessions.py
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.project_registry import ProjectRegistry
from core.session_manager import SessionManager

logger = logging.getLogger(__name__)

# Conversation states
SELECT_PROJECT, SELECT_MODE, ENTER_PROMPT = range(3)

# Callback data
CB_SESSIONS = "sessions"
CB_NEW_SESSION = "new_session"
CB_SESSION_PROJECT = "sess_proj:"
CB_SESSION_MODE = "sess_mode:"
CB_SESSION_KILL = "sess_kill:"
CB_BACK_MAIN = "main_menu"


def create_session_handlers(
    registry: ProjectRegistry,
    session_manager: SessionManager,
    auth_check,
):

    @auth_check
    async def show_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query:
            await query.answer()

        sessions = session_manager.list_sessions()
        if not sessions:
            text = "📋 Нет активных сессий"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)]]
        else:
            lines = ["📋 <b>Активные сессии:</b>\n"]
            keyboard = []
            for s in sessions:
                mode_label = "remote" if s.mode == "remote" else "обычная"
                lines.append(
                    f"  • <b>{s.project_name}</b> — {mode_label} — {s.duration_minutes()} мин"
                )
                keyboard.append([
                    InlineKeyboardButton(
                        f"❌ {s.project_name}", callback_data=f"{CB_SESSION_KILL}{s.session_id}"
                    )
                ])
            text = "\n".join(lines)
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)])

        msg_kwargs = dict(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        if query:
            await query.edit_message_text(**msg_kwargs)
        else:
            await update.message.reply_text(**msg_kwargs)

    @auth_check
    async def kill_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        session_id = query.data.replace(CB_SESSION_KILL, "")

        killed = await session_manager.kill_session(session_id)
        text = "✅ Сессия завершена" if killed else "⚠️ Сессия не найдена"

        keyboard = [[InlineKeyboardButton("🔙 К сессиям", callback_data=CB_SESSIONS)]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    # --- New session wizard ---

    @auth_check
    async def wizard_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        projects = registry.list()
        if not projects:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)]]
            await query.edit_message_text(
                "Нет зарегистрированных проектов. Сначала добавь проект.",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(p["name"], callback_data=f"{CB_SESSION_PROJECT}{p['name']}")]
            for p in projects
        ]
        keyboard.append([InlineKeyboardButton("🔙 Отмена", callback_data=CB_BACK_MAIN)])

        await query.edit_message_text(
            "Какой проект?", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_PROJECT

    @auth_check
    async def wizard_select_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if query.data == CB_BACK_MAIN:
            return ConversationHandler.END

        project_name = query.data.replace(CB_SESSION_PROJECT, "")
        context.user_data["session_project"] = project_name

        keyboard = [
            [InlineKeyboardButton("🖥️ Remote Control", callback_data=f"{CB_SESSION_MODE}remote")],
            [InlineKeyboardButton("▶️ Обычная", callback_data=f"{CB_SESSION_MODE}normal")],
            [InlineKeyboardButton("🔙 Отмена", callback_data=CB_BACK_MAIN)],
        ]
        await query.edit_message_text(
            f"Проект: <b>{project_name}</b>\nРежим?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )
        return SELECT_MODE

    @auth_check
    async def wizard_select_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if query.data == CB_BACK_MAIN:
            return ConversationHandler.END

        mode = query.data.replace(CB_SESSION_MODE, "")
        context.user_data["session_mode"] = mode

        await query.edit_message_text(
            "Введи промпт (или /skip для пустой сессии):"
        )
        return ENTER_PROMPT

    @auth_check
    async def wizard_enter_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
        prompt = update.message.text
        if prompt == "/skip":
            prompt = ""

        project_name = context.user_data.get("session_project")
        mode = context.user_data.get("session_mode")

        project = registry.get(project_name)
        if not project:
            await update.message.reply_text("⚠️ Проект не найден")
            return ConversationHandler.END

        await update.message.reply_text(f"⏳ Запускаю {mode} сессию для <b>{project_name}</b>...", parse_mode="HTML")

        if mode == "remote":
            await session_manager.start_remote(project_name, project["path"], prompt)
        else:
            if not prompt:
                await update.message.reply_text("⚠️ Для обычного режима нужен промпт")
                return ConversationHandler.END
            await session_manager.start_normal(project_name, project["path"], prompt)

        return ConversationHandler.END

    @auth_check
    async def wizard_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
        return ConversationHandler.END

    wizard_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(wizard_start, pattern=f"^{CB_NEW_SESSION}$")],
        states={
            SELECT_PROJECT: [CallbackQueryHandler(wizard_select_project)],
            SELECT_MODE: [CallbackQueryHandler(wizard_select_mode)],
            ENTER_PROMPT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_enter_prompt),
                MessageHandler(filters.Regex(r"^/skip$"), wizard_enter_prompt),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(wizard_cancel, pattern=f"^{CB_BACK_MAIN}$"),
        ],
        per_message=False,
    )

    return [
        wizard_conversation,
        CallbackQueryHandler(show_sessions, pattern=f"^{CB_SESSIONS}$"),
        CallbackQueryHandler(kill_session, pattern=f"^{CB_SESSION_KILL}"),
    ]
```

- [ ] **Step 2: Commit**

```bash
git add handlers/sessions.py
git commit -m "feat: session wizard and active sessions handlers"
```

---

### Task 12: Telegram Handlers — Settings

**Files:**
- Create: `handlers/settings.py`

- [ ] **Step 1: Implement settings handler**

```python
# handlers/settings.py
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

logger = logging.getLogger(__name__)

CB_SETTINGS = "settings"
CB_BACK_MAIN = "main_menu"


def create_settings_handlers(auth_check):

    @auth_check
    async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        cfg = context.bot_data.get("config")
        text = (
            "⚙️ <b>Настройки</b>\n\n"
            f"📁 Директория проектов: <code>{cfg.projects_dir or 'не задана'}</code>\n"
            f"⏱️ Интервал поллинга: {cfg.poll_interval_sec} сек\n"
            f"📊 Пороги: {', '.join(str(t) + '%' for t in cfg.thresholds)}\n"
            f"📝 Уровень логов: {cfg.log_level}\n\n"
            "<i>Для изменения отредактируй config.json и перезапусти бота</i>"
        )
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)]]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )

    return [
        CallbackQueryHandler(show_settings, pattern=f"^{CB_SETTINGS}$"),
    ]
```

- [ ] **Step 2: Commit**

```bash
git add handlers/settings.py
git commit -m "feat: settings handler showing current configuration"
```

---

### Task 13: Analytics Telegram Handlers

**Files:**
- Create: `analytics/handlers.py`

- [ ] **Step 1: Implement analytics handlers**

```python
# analytics/handlers.py
import logging
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from analytics.charts import UsageCharts
from core.limit_tracker import LimitTracker

logger = logging.getLogger(__name__)

CB_LIMITS = "limits"
CB_BACK_MAIN = "main_menu"


def _format_usage_text(limit_tracker: LimitTracker) -> str | None:
    usage = limit_tracker.latest
    if not usage:
        return None

    five_pct = round(usage.five_hour_util * 100, 1)
    seven_pct = round(usage.seven_day_util * 100, 1)
    sonnet_pct = round(usage.seven_day_sonnet_util * 100, 1)

    reset_5h = ""
    if usage.five_hour_resets_at:
        try:
            dt = datetime.fromisoformat(usage.five_hour_resets_at)
            mins = max(0, int((dt - datetime.now(timezone.utc)).total_seconds() / 60))
            reset_5h = f" (reset через {mins} мин)"
        except ValueError:
            pass

    return (
        f"📊 <b>Использование лимитов</b>\n\n"
        f"⏱️ 5h: <b>{five_pct}%</b>{reset_5h}\n"
        f"📅 7d: <b>{seven_pct}%</b>\n"
        f"🤖 7d sonnet: <b>{sonnet_pct}%</b>"
    )


def create_analytics_handlers(
    limit_tracker: LimitTracker,
    charts: UsageCharts,
    auth_check,
):

    @auth_check
    async def show_limits(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle both /usage command and inline button press."""
        text = _format_usage_text(limit_tracker)
        if not text:
            text = "📊 Данные ещё не загружены, подожди немного"

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)]]

        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
            )
        else:
            await update.message.reply_text(text, parse_mode="HTML")

    @auth_check
    async def cmd_usage_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = charts.generate_day(today)
        if not path:
            await update.message.reply_text("📊 Нет данных за сегодня")
            return
        with open(path, "rb") as f:
            await update.message.reply_photo(photo=f, caption=f"📊 Usage — {today}")

    @auth_check
    async def cmd_usage_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = charts.generate_week(today)
        if not path:
            await update.message.reply_text("📊 Нет данных за неделю")
            return
        with open(path, "rb") as f:
            await update.message.reply_photo(photo=f, caption=f"📊 Usage — week ending {today}")

    @auth_check
    async def cmd_usage_heatmap(update: Update, context: ContextTypes.DEFAULT_TYPE):
        year_month = datetime.now(timezone.utc).strftime("%Y-%m")
        path = charts.generate_heatmap(year_month)
        if not path:
            await update.message.reply_text("📊 Нет данных за этот месяц")
            return
        with open(path, "rb") as f:
            await update.message.reply_photo(photo=f, caption=f"📊 Heatmap — {year_month}")

    return [
        CallbackQueryHandler(show_limits, pattern=f"^{CB_LIMITS}$"),
        CommandHandler("usage", show_limits),
        CommandHandler("usage_day", cmd_usage_day),
        CommandHandler("usage_week", cmd_usage_week),
        CommandHandler("usage_heatmap", cmd_usage_heatmap),
    ]
```

- [ ] **Step 2: Commit**

```bash
git add analytics/handlers.py
git commit -m "feat: analytics Telegram commands — usage, charts, heatmap"
```

---

### Task 14: Bot Entry Point

**Files:**
- Create: `bot.py`

- [ ] **Step 1: Implement bot.py**

```python
# bot.py
import asyncio
import logging
import sys

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, ContextTypes, CallbackQueryHandler, CommandHandler

from config import load_config, get_claude_credentials_path
from core.notifier import Notifier
from core.project_registry import ProjectRegistry
from core.session_manager import SessionManager
from core.limit_tracker import LimitTracker
from analytics.collector import UsageCollector
from analytics.charts import UsageCharts
from analytics.handlers import create_analytics_handlers
from handlers.auth import authorized
from handlers.projects import create_project_handlers
from handlers.sessions import create_session_handlers
from handlers.settings import create_settings_handlers

logger = logging.getLogger(__name__)

CB_BACK_MAIN = "main_menu"
CB_LIMITS = "limits"


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📂 Проекты", callback_data="projects")],
        [InlineKeyboardButton("🚀 Новая сессия", callback_data="new_session")],
        [InlineKeyboardButton("📋 Сессии", callback_data="sessions")],
        [InlineKeyboardButton("📊 Лимиты", callback_data=CB_LIMITS)],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
    ]
    text = "🏠 <b>Claude Dispatcher</b>"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )


def main():
    cfg = load_config()

    logging.basicConfig(
        level=getattr(logging, cfg.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/bot.log", encoding="utf-8"),
        ],
    )

    app = Application.builder().token(cfg.telegram_bot_token).build()

    bot_instance: Bot = app.bot
    auth_check = authorized(cfg.telegram_user_id)

    # Core components
    notifier = Notifier(bot=bot_instance, chat_id=cfg.telegram_user_id)
    registry = ProjectRegistry(data_file="data/projects.json")
    session_manager = SessionManager(notifier=notifier)

    # Analytics
    collector = UsageCollector(data_dir="data/usage")
    charts = UsageCharts(collector=collector, output_dir="data/charts")

    # Limit tracker with collector callback
    limit_tracker = LimitTracker(
        notifier=notifier,
        thresholds=cfg.thresholds,
        poll_interval_sec=cfg.poll_interval_sec,
        credentials_path=get_claude_credentials_path(),
        on_usage=collector.record,
    )

    # Store config in bot_data for handlers
    app.bot_data["config"] = cfg

    # Register handlers
    # Main menu
    start_handler = CommandHandler("start", auth_check(main_menu))
    back_handler = CallbackQueryHandler(auth_check(main_menu), pattern=f"^{CB_BACK_MAIN}$")

    app.add_handler(start_handler)
    app.add_handler(back_handler)

    # Session handlers (ConversationHandler must be added before simple CallbackQueryHandlers)
    for handler in create_session_handlers(registry, session_manager, auth_check):
        app.add_handler(handler)

    # Project handlers
    for handler in create_project_handlers(registry, auth_check):
        app.add_handler(handler)

    # Settings handlers
    for handler in create_settings_handlers(auth_check):
        app.add_handler(handler)

    # Analytics handlers
    for handler in create_analytics_handlers(limit_tracker, charts, auth_check):
        app.add_handler(handler)

    # Start limit tracker after app starts
    async def post_init(application: Application):
        limit_tracker.start()
        logger.info("Bot started. Limit tracker polling every %ds", cfg.poll_interval_sec)

    async def post_shutdown(application: Application):
        limit_tracker.stop()

    app.post_init = post_init
    app.post_shutdown = post_shutdown

    logger.info("Starting Claude Dispatcher Bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create logs directory placeholder**

```bash
mkdir -p logs
```

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat: bot entry point wiring all components together"
```

---

### Task 15: Smoke Test

- [ ] **Step 1: Run all unit tests**

Run: `python -m pytest tests/ -v`
Expected: all tests PASS

- [ ] **Step 2: Verify imports work**

Run: `python -c "from bot import main; print('OK')"`
Expected: prints `OK` (requires dependencies installed)

- [ ] **Step 3: Commit any remaining fixes**

```bash
git add -A
git commit -m "chore: smoke test fixes"
```

---

### Task 16: Distribution Files

**Files:**
- Create: `.env.example` (already exists, verify)
- Create: `config.example.json` (already exists, verify)

- [ ] **Step 1: Verify .env.example and config.example.json are up to date**

`.env.example` should contain:
```
# Telegram bot token from @BotFather
TELEGRAM_BOT_TOKEN=
# Your Telegram user ID (get it from @userinfobot)
TELEGRAM_USER_ID=
```

`config.example.json` should contain:
```json
{
  "projects_dir": "E:\\",
  "poll_interval_sec": 60,
  "thresholds": [70, 85, 95],
  "log_level": "INFO"
}
```

- [ ] **Step 2: Final commit**

```bash
git add .env.example config.example.json
git commit -m "chore: verify distribution files"
```
