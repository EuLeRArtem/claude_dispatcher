# Token Cost Tracking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Empirically measure token cost in % utilization per Claude Code session, store per-session cost data, visualize unit cost on a chart in Telegram.

**Architecture:** On session start, snapshot current utilization. On Stop hook, parse the JSONL transcript for token usage, poll utilization again, compute delta, write to CSV. New chart type shows unit cost (% per 1K tokens) over time. Stub alert method for future high-cost warnings.

**Tech Stack:** Python 3.13, aiohttp, matplotlib, pytest, pytest-asyncio, pytest-aiohttp

---

### Task 1: Transcript Parser

**Files:**
- Create: `core/transcript_parser.py`
- Test: `tests/test_transcript_parser.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_transcript_parser.py
import json
import pytest
from pathlib import Path

from core.transcript_parser import parse_transcript, SessionUsage


@pytest.fixture
def transcript_file(tmp_path):
    """Create a minimal JSONL transcript with 3 assistant messages."""
    lines = [
        {"type": "system", "subtype": "bridge_status", "content": "ready", "timestamp": "2026-04-12T10:00:00Z"},
        {"type": "human", "content": [{"type": "text", "text": "hello"}], "timestamp": "2026-04-12T10:01:00Z"},
        {
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-6",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 500,
                    "cache_read_input_tokens": 5000,
                    "cache_creation_input_tokens": 200,
                },
            },
            "timestamp": "2026-04-12T10:01:05Z",
        },
        {"type": "human", "content": [{"type": "text", "text": "fix bug"}], "timestamp": "2026-04-12T10:02:00Z"},
        {
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-6",
                "usage": {
                    "input_tokens": 150,
                    "output_tokens": 800,
                    "cache_read_input_tokens": 6000,
                    "cache_creation_input_tokens": 0,
                },
            },
            "timestamp": "2026-04-12T10:02:10Z",
        },
        {
            "type": "assistant",
            "message": {
                "model": "claude-haiku-4-5-20251001",
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 100,
                    "cache_read_input_tokens": 1000,
                    "cache_creation_input_tokens": 0,
                },
            },
            "timestamp": "2026-04-12T10:03:00Z",
        },
    ]
    p = tmp_path / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(l) for l in lines), encoding="utf-8")
    return str(p)


def test_parse_transcript_sums_usage(transcript_file):
    result = parse_transcript(transcript_file)
    assert result is not None
    assert result.input_tokens == 300        # 100 + 150 + 50
    assert result.output_tokens == 1400      # 500 + 800 + 100
    assert result.cache_read_input_tokens == 12000  # 5000 + 6000 + 1000
    assert result.cache_creation_input_tokens == 200
    assert result.request_count == 3


def test_parse_transcript_picks_most_common_model(transcript_file):
    result = parse_transcript(transcript_file)
    assert result is not None
    assert result.model == "claude-opus-4-6"  # 2 opus vs 1 haiku


def test_parse_transcript_missing_file():
    result = parse_transcript("/nonexistent/path.jsonl")
    assert result is None


def test_parse_transcript_no_assistant_messages(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text(json.dumps({"type": "system", "content": "init"}), encoding="utf-8")
    result = parse_transcript(str(p))
    assert result is None


def test_parse_transcript_missing_usage_fields(tmp_path):
    """Assistant message with partial usage — missing fields default to 0."""
    line = {
        "type": "assistant",
        "message": {
            "model": "claude-opus-4-6",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        },
    }
    p = tmp_path / "partial.jsonl"
    p.write_text(json.dumps(line), encoding="utf-8")
    result = parse_transcript(str(p))
    assert result is not None
    assert result.cache_read_input_tokens == 0
    assert result.cache_creation_input_tokens == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_transcript_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.transcript_parser'`

- [ ] **Step 3: Implement transcript parser**

```python
# core/transcript_parser.py
import json
import logging
from collections import Counter
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SessionUsage:
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    request_count: int


def parse_transcript(path: str) -> SessionUsage | None:
    """Parse a Claude Code JSONL transcript and sum token usage."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except (FileNotFoundError, OSError):
        logger.warning("Transcript not found: %s", path)
        return None

    models: list[str] = []
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }

    for line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "assistant" or "message" not in obj:
            continue
        msg = obj["message"]
        usage = msg.get("usage", {})
        model = msg.get("model", "unknown")
        models.append(model)
        for key in totals:
            totals[key] += usage.get(key, 0)

    if not models:
        return None

    most_common_model = Counter(models).most_common(1)[0][0]
    return SessionUsage(
        model=most_common_model,
        request_count=len(models),
        **totals,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_transcript_parser.py -v`
Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/transcript_parser.py tests/test_transcript_parser.py
git commit -m "feat: add transcript parser for token usage extraction"
```

---

### Task 2: Cost Tracker (Storage)

**Files:**
- Create: `core/cost_tracker.py`
- Test: `tests/test_cost_tracker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cost_tracker.py
import csv
import pytest
from pathlib import Path

from core.cost_tracker import CostTracker, SessionCost


def _make_cost(**overrides) -> SessionCost:
    defaults = dict(
        timestamp="2026-04-12T19:15:00+00:00",
        session_id="abc123",
        project="test-project",
        model="claude-opus-4-6",
        input_tokens=1000,
        output_tokens=5000,
        cache_read_tokens=100000,
        cache_creation_tokens=2000,
        request_count=10,
        util_before_5h=0.05,
        util_after_5h=0.15,
        util_before_7d=0.30,
        util_after_7d=0.31,
        delta_5h=0.10,
        delta_7d=0.01,
        concurrent=False,
        duration_min=25,
    )
    defaults.update(overrides)
    return SessionCost(**defaults)


def test_record_creates_csv(tmp_path):
    tracker = CostTracker(data_dir=str(tmp_path))
    tracker.record(_make_cost())
    csv_path = tmp_path / "2026-04.csv"
    assert csv_path.exists()
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["session_id"] == "abc123"
    assert rows[0]["output_tokens"] == "5000"
    assert rows[0]["delta_5h"] == "0.1"


def test_record_appends_to_existing(tmp_path):
    tracker = CostTracker(data_dir=str(tmp_path))
    tracker.record(_make_cost(session_id="s1"))
    tracker.record(_make_cost(session_id="s2"))
    rows = tracker.load("2026-04")
    assert len(rows) == 2
    assert rows[0]["session_id"] == "s1"
    assert rows[1]["session_id"] == "s2"


def test_load_empty_month(tmp_path):
    tracker = CostTracker(data_dir=str(tmp_path))
    assert tracker.load("2025-01") == []


def test_record_with_null_util(tmp_path):
    """When snapshot failed, util_before fields are empty strings."""
    tracker = CostTracker(data_dir=str(tmp_path))
    cost = _make_cost(util_before_5h="", util_before_7d="", delta_5h="", delta_7d="")
    tracker.record(cost)
    rows = tracker.load("2026-04")
    assert len(rows) == 1
    assert rows[0]["util_before_5h"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cost_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.cost_tracker'`

- [ ] **Step 3: Implement cost tracker**

```python
# core/cost_tracker.py
import csv
import logging
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

FIELDNAMES = [
    "timestamp", "session_id", "project", "model",
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens",
    "request_count",
    "util_before_5h", "util_after_5h", "util_before_7d", "util_after_7d",
    "delta_5h", "delta_7d",
    "concurrent", "duration_min",
]


@dataclass
class SessionCost:
    timestamp: str
    session_id: str
    project: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    request_count: int
    util_before_5h: float | str  # "" when snapshot failed
    util_after_5h: float | str
    util_before_7d: float | str
    util_after_7d: float | str
    delta_5h: float | str
    delta_7d: float | str
    concurrent: bool
    duration_min: int


class CostTracker:
    def __init__(self, data_dir: str = "data/costs"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _csv_path(self, timestamp: str) -> Path:
        dt = datetime.fromisoformat(timestamp)
        return self._data_dir / f"{dt.strftime('%Y-%m')}.csv"

    def record(self, cost: SessionCost) -> None:
        csv_path = self._csv_path(cost.timestamp)
        file_exists = csv_path.exists()
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow({field.name: getattr(cost, field.name) for field in fields(cost)})

    def load(self, year_month: str) -> list[dict]:
        csv_path = self._data_dir / f"{year_month}.csv"
        if not csv_path.exists():
            return []
        with open(csv_path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cost_tracker.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/cost_tracker.py tests/test_cost_tracker.py
git commit -m "feat: add cost tracker for per-session cost storage"
```

---

### Task 3: Make `poll_once()` Public in LimitTracker

**Files:**
- Modify: `core/limit_tracker.py` (rename `_poll_once` → `poll_once`)
- Modify: `tests/test_limit_tracker.py` (if any tests reference `_poll_once`)

- [ ] **Step 1: Check for existing references to `_poll_once`**

Run: `grep -rn "_poll_once" core/ tests/`
The method is called in `_poll_loop` and possibly tests. All internal `_poll_once` references need renaming.

- [ ] **Step 2: Rename `_poll_once` to `poll_once`**

In `core/limit_tracker.py`, replace all occurrences of `_poll_once` with `poll_once`:
- Method definition: `async def _poll_once(self)` → `async def poll_once(self)`
- Call in `_poll_loop`: `await self._poll_once()` → `await self.poll_once()`

- [ ] **Step 3: Run existing tests**

Run: `pytest tests/test_limit_tracker.py -v`
Expected: all existing tests PASS (no tests call `_poll_once` directly)

- [ ] **Step 4: Commit**

```bash
git add core/limit_tracker.py
git commit -m "refactor: make poll_once() public in LimitTracker"
```

---

### Task 4: Add `util_snapshot` to SessionInfo and Capture on Start

**Files:**
- Modify: `core/session_manager.py`
- Test: `tests/test_session_manager.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_session_manager.py`:

```python
# Add at top with other imports
from core.limit_tracker import UsageData

# New test
@pytest.mark.asyncio
async def test_start_normal_captures_util_snapshot(session_manager):
    """Starting a session should poll utilization and store snapshot."""
    snapshot = UsageData(five_hour_util=0.1, seven_day_util=0.3)
    session_manager._limit_tracker = AsyncMock()
    session_manager._limit_tracker.poll_once = AsyncMock(return_value=snapshot)

    info = await session_manager.start_normal("proj", "/tmp/proj", "do stuff")
    assert info.util_snapshot is not None
    assert info.util_snapshot.five_hour_util == 0.1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_manager.py::test_start_normal_captures_util_snapshot -v`
Expected: FAIL — `SessionInfo` has no attribute `util_snapshot`

- [ ] **Step 3: Implement changes**

In `core/session_manager.py`:

1. Add import at top:
```python
from core.limit_tracker import UsageData
```

2. Add field to `SessionInfo`:
```python
util_snapshot: UsageData | None = None  # utilization at session start
```

3. Add `limit_tracker` parameter to `SessionManager.__init__`:
```python
def __init__(self, notifier: Notifier, ide: str = "none", ide_trigger_timeout: int = 30, limit_tracker=None):
    self._notifier = notifier
    self._ide = ide
    self._ide_trigger_timeout = ide_trigger_timeout
    self._sessions: dict[str, SessionInfo] = {}
    self._limit_tracker = limit_tracker
```

4. Add snapshot helper method:
```python
async def _capture_util_snapshot(self) -> UsageData | None:
    if self._limit_tracker is None:
        return None
    try:
        return await self._limit_tracker.poll_once()
    except Exception:
        logger.warning("Failed to capture util snapshot", exc_info=True)
        return None
```

5. In `start_normal()`, before creating `SessionInfo`:
```python
snapshot = await self._capture_util_snapshot()
```
And add `util_snapshot=snapshot` to `SessionInfo(...)`.

6. In `start_remote()` (Unix path), same pattern:
```python
snapshot = await self._capture_util_snapshot()
```
And add `util_snapshot=snapshot` to `SessionInfo(...)`.

7. In `_start_remote_console()`, same pattern:
```python
snapshot = await self._capture_util_snapshot()
```
And add `util_snapshot=snapshot` to `SessionInfo(...)`.

8. In `_start_remote_ide()`, same pattern:
```python
snapshot = await self._capture_util_snapshot()
```
And add `util_snapshot=snapshot` to `SessionInfo(...)`.

- [ ] **Step 4: Update existing tests to pass `limit_tracker=None`**

The `SessionManager` constructor now has an optional `limit_tracker` param with default `None`, so existing tests should pass without changes. Verify:

Run: `pytest tests/test_session_manager.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/session_manager.py tests/test_session_manager.py
git commit -m "feat: capture utilization snapshot on session start"
```

---

### Task 5: Wire Cost Tracking into HookServer

**Files:**
- Modify: `core/hook_server.py`
- Modify: `tests/test_hook_server.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_hook_server.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch
from core.limit_tracker import UsageData
from core.cost_tracker import SessionCost


@pytest.fixture
def cost_tracker():
    ct = MagicMock()
    ct.record = MagicMock()
    return ct


@pytest.fixture
def limit_tracker():
    lt = MagicMock()
    lt.poll_once = AsyncMock(return_value=UsageData(
        five_hour_util=0.20, seven_day_util=0.35,
        five_hour_resets_at="", seven_day_resets_at="",
        timestamp="2026-04-12T19:15:00+00:00",
    ))
    return lt


@pytest.fixture
def hook_server_with_cost(notifier, session_manager, cost_tracker, limit_tracker):
    return HookServer(
        notifier=notifier, session_manager=session_manager,
        cost_tracker=cost_tracker, limit_tracker=limit_tracker, port=0,
    )


@pytest.fixture
def app_with_cost(hook_server_with_cost):
    return hook_server_with_cost.create_app()


@pytest.fixture
def client_with_cost(aiohttp_client, app_with_cost):
    return aiohttp_client(app_with_cost)


@pytest.mark.asyncio
async def test_stop_records_cost(client_with_cost, cost_tracker, session_manager):
    session_info = MagicMock()
    session_info.project_name = "my-proj"
    session_info.url = None
    session_info.session_id = "s1"
    session_info.util_snapshot = UsageData(
        five_hour_util=0.10, seven_day_util=0.30,
        five_hour_resets_at="", seven_day_resets_at="",
        timestamp="2026-04-12T19:00:00+00:00",
    )
    session_info.duration_minutes.return_value = 15
    session_manager.list_sessions.return_value = [session_info]

    fake_usage = MagicMock()
    fake_usage.model = "claude-opus-4-6"
    fake_usage.input_tokens = 100
    fake_usage.output_tokens = 500
    fake_usage.cache_read_input_tokens = 5000
    fake_usage.cache_creation_input_tokens = 200
    fake_usage.request_count = 3

    cl = await client_with_cost
    with patch("core.hook_server.parse_transcript", return_value=fake_usage):
        resp = await cl.post("/hooks", json={
            "hook_event_name": "Stop",
            "session_id": "claude-id",
            "cwd": "/tmp/proj",
            "transcript_path": "/tmp/transcript.jsonl",
            "last_assistant_message": "Done.",
        })

    assert resp.status == 200
    cost_tracker.record.assert_called_once()
    cost = cost_tracker.record.call_args[0][0]
    assert cost.project == "my-proj"
    assert cost.model == "claude-opus-4-6"
    assert cost.output_tokens == 500
    assert cost.delta_5h == pytest.approx(0.10)  # 0.20 - 0.10
    assert cost.delta_7d == pytest.approx(0.05)  # 0.35 - 0.30
    assert cost.concurrent is False


@pytest.mark.asyncio
async def test_stop_without_transcript_still_works(client_with_cost, cost_tracker, notifier):
    cl = await client_with_cost
    resp = await cl.post("/hooks", json={
        "hook_event_name": "Stop",
        "session_id": "abc",
        "cwd": "/tmp/proj",
        "last_assistant_message": "Done.",
    })
    assert resp.status == 200
    notifier.send.assert_called_once()
    # No transcript_path → no cost record
    cost_tracker.record.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_hook_server.py::test_stop_records_cost -v`
Expected: FAIL — `HookServer.__init__() got unexpected keyword argument 'cost_tracker'`

- [ ] **Step 3: Implement changes to hook_server.py**

In `core/hook_server.py`:

1. Add imports at top:
```python
from core.transcript_parser import parse_transcript
from core.cost_tracker import CostTracker, SessionCost
from core.limit_tracker import LimitTracker
from datetime import datetime, timezone
```

2. Update `__init__`:
```python
def __init__(self, notifier: Notifier, session_manager, port: int = 9384,
             cost_tracker: CostTracker | None = None, limit_tracker: LimitTracker | None = None):
    self._notifier = notifier
    self._session_manager = session_manager
    self._port = port
    self._cost_tracker = cost_tracker
    self._limit_tracker = limit_tracker
```

3. Add cost recording method:
```python
async def _record_session_cost(self, data: dict, project: str, session) -> None:
    """Parse transcript, poll utilization, compute delta, record cost."""
    transcript_path = data.get("transcript_path")
    if not transcript_path or not self._cost_tracker:
        return

    usage = parse_transcript(transcript_path)
    if not usage:
        logger.warning("Could not parse transcript: %s", transcript_path)
        return

    # Poll current utilization
    util_after = None
    if self._limit_tracker:
        util_after = await self._limit_tracker.poll_once()

    # Get snapshot from session
    util_before = session.util_snapshot if session else None

    # Compute deltas
    if util_before and util_after:
        delta_5h = util_after.five_hour_util - util_before.five_hour_util
        delta_7d = util_after.seven_day_util - util_before.seven_day_util
        before_5h = util_before.five_hour_util
        before_7d = util_before.seven_day_util
        after_5h = util_after.five_hour_util
        after_7d = util_after.seven_day_util
    else:
        delta_5h = ""
        delta_7d = ""
        before_5h = util_before.five_hour_util if util_before else ""
        before_7d = util_before.seven_day_util if util_before else ""
        after_5h = util_after.five_hour_util if util_after else ""
        after_7d = util_after.seven_day_util if util_after else ""

    active_sessions = self._session_manager.list_sessions()
    concurrent = len(active_sessions) > 1

    duration_min = session.duration_minutes() if session else 0

    cost = SessionCost(
        timestamp=datetime.now(timezone.utc).isoformat(),
        session_id=session.session_id if session else data.get("session_id", ""),
        project=project,
        model=usage.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_input_tokens,
        cache_creation_tokens=usage.cache_creation_input_tokens,
        request_count=usage.request_count,
        util_before_5h=before_5h,
        util_after_5h=after_5h,
        util_before_7d=before_7d,
        util_after_7d=after_7d,
        delta_5h=delta_5h,
        delta_7d=delta_7d,
        concurrent=concurrent,
        duration_min=duration_min,
    )
    self._cost_tracker.record(cost)
    logger.info("Recorded session cost: %s %s Δ5h=%.2f%% Δ7d=%.2f%%",
                project, usage.model,
                delta_5h * 100 if isinstance(delta_5h, float) else 0,
                delta_7d * 100 if isinstance(delta_7d, float) else 0)
```

4. Update `_handle_hook` Stop block — add `_record_session_cost` call after the existing notification:
```python
if event == "Stop":
    last_msg = data.get("last_assistant_message", "")
    truncated = last_msg[:300] + "..." if len(last_msg) > 300 else last_msg
    from core.notifier import _MENU_KB
    await self._notifier.send(
        f"✅ <b>{project}</b>: задача завершена\n<pre>{truncated}</pre>",
        reply_markup=_MENU_KB,
    )
    # Record session cost
    session = self._find_session_by_cwd(data.get("cwd", ""))
    await self._record_session_cost(data, project, session)
```

- [ ] **Step 4: Update existing tests — ensure old fixtures still work**

The `HookServer.__init__` now has optional `cost_tracker` and `limit_tracker` with default `None`, so existing tests pass unchanged. Verify:

Run: `pytest tests/test_hook_server.py -v`
Expected: all tests PASS (old + new)

- [ ] **Step 5: Commit**

```bash
git add core/hook_server.py tests/test_hook_server.py
git commit -m "feat: record session cost on Stop hook"
```

---

### Task 6: Wire CostTracker and LimitTracker into bot.py

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Add imports and create CostTracker**

In `bot.py`, add import:
```python
from core.cost_tracker import CostTracker
```

After the `collector` line (~line 76), add:
```python
cost_tracker = CostTracker(data_dir="data/costs")
```

- [ ] **Step 2: Pass limit_tracker to SessionManager**

Change the `session_manager` line:
```python
session_manager = SessionManager(
    notifier=notifier, ide=cfg.ide,
    ide_trigger_timeout=cfg.ide_trigger_timeout,
    limit_tracker=limit_tracker,
)
```

Note: `limit_tracker` is created after `session_manager` currently. Reorder: move `limit_tracker` creation before `session_manager`.

New order in `bot.py`:
```python
# Core components
notifier = Notifier(bot=bot_instance, chat_id=cfg.telegram_user_id)
registry = ProjectRegistry(data_file="data/projects.json")

# Analytics
collector = UsageCollector(data_dir="data/usage")
charts = UsageCharts(collector=collector, output_dir="data/charts")
cost_tracker = CostTracker(data_dir="data/costs")

# Limit tracker (before session_manager — needed for util snapshots)
limit_tracker = LimitTracker(
    notifier=notifier,
    thresholds=cfg.thresholds,
    poll_interval_sec=cfg.poll_interval_sec,
    credentials_path=get_claude_credentials_path(),
    on_usage=collector.record,
)

session_manager = SessionManager(
    notifier=notifier, ide=cfg.ide,
    ide_trigger_timeout=cfg.ide_trigger_timeout,
    limit_tracker=limit_tracker,
)
hook_server = HookServer(
    notifier=notifier, session_manager=session_manager,
    cost_tracker=cost_tracker, limit_tracker=limit_tracker,
    port=cfg.hook_port,
)
```

- [ ] **Step 3: Run the bot briefly to verify no import/init errors**

Run: `python -c "from bot import main; print('OK')"`
Expected: prints `OK` without errors

- [ ] **Step 4: Commit**

```bash
git add bot.py
git commit -m "feat: wire cost tracker into bot lifecycle"
```

---

### Task 7: Token Cost Chart

**Files:**
- Modify: `analytics/charts.py`
- Test: `tests/test_charts.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_charts.py`:

```python
from unittest.mock import MagicMock
from analytics.charts import UsageCharts


def test_generate_token_cost_returns_path(tmp_path):
    """Token cost chart should be generated from cost data."""
    cost_tracker = MagicMock()
    cost_tracker.load.return_value = [
        {
            "timestamp": "2026-04-12T10:00:00+00:00",
            "model": "claude-opus-4-6",
            "output_tokens": "5000",
            "delta_5h": "0.05",
            "concurrent": "False",
        },
        {
            "timestamp": "2026-04-12T14:00:00+00:00",
            "model": "claude-opus-4-6",
            "output_tokens": "10000",
            "delta_5h": "0.08",
            "concurrent": "False",
        },
    ]
    collector = MagicMock()
    collector.load.return_value = []
    charts = UsageCharts(collector=collector, output_dir=str(tmp_path), cost_tracker=cost_tracker)
    result = charts.generate_token_cost("2026-04-12")
    assert result is not None
    assert result.endswith(".png")
    assert Path(result).exists()


def test_generate_token_cost_no_data(tmp_path):
    cost_tracker = MagicMock()
    cost_tracker.load.return_value = []
    collector = MagicMock()
    collector.load.return_value = []
    charts = UsageCharts(collector=collector, output_dir=str(tmp_path), cost_tracker=cost_tracker)
    result = charts.generate_token_cost("2026-04-12")
    assert result is None
```

Add `from pathlib import Path` at top of test file if not already present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_charts.py::test_generate_token_cost_returns_path -v`
Expected: FAIL — `UsageCharts.__init__() got unexpected keyword argument 'cost_tracker'`

- [ ] **Step 3: Implement chart**

In `analytics/charts.py`:

1. Update `__init__` to accept optional `cost_tracker`:
```python
def __init__(self, collector: UsageCollector, output_dir: str = "data/charts", cost_tracker=None):
    self._collector = collector
    self._cost_tracker = cost_tracker
    self._output_dir = Path(output_dir)
    self._output_dir.mkdir(parents=True, exist_ok=True)
```

2. Add color map for models at module level:
```python
_MODEL_COLORS = {
    "claude-opus-4-6": "#7C3AED",       # purple
    "claude-sonnet-4-6": "#2563EB",      # blue
    "claude-haiku-4-5-20251001": "#10B981",  # green
}
_DEFAULT_COLOR = "#6B7280"  # gray
```

3. Add `generate_token_cost` method:
```python
def generate_token_cost(self, date_str: str) -> str | None:
    """Generate scatter plot: unit cost (% per 1K output tokens) over time."""
    if not self._cost_tracker:
        return None

    year_month = date_str[:7]
    rows = self._cost_tracker.load(year_month)

    # Filter: need numeric delta_5h and output_tokens > 0
    valid = []
    for row in rows:
        try:
            delta = float(row["delta_5h"])
            out_tokens = int(row["output_tokens"])
            if out_tokens <= 0:
                continue
            valid.append(row)
        except (ValueError, KeyError):
            continue

    if not valid:
        return None

    times = [datetime.fromisoformat(r["timestamp"]) for r in valid]
    costs = [float(r["delta_5h"]) / int(r["output_tokens"]) * 1000 * 100 for r in valid]  # % per 1K
    models = [r.get("model", "unknown") for r in valid]
    concurrent = [r.get("concurrent", "False") == "True" for r in valid]

    fig, ax = plt.subplots(figsize=(10, 5))

    # Plot by model
    for model in set(models):
        color = _MODEL_COLORS.get(model, _DEFAULT_COLOR)
        label = model.split("-")[1] if "-" in model else model  # "opus", "sonnet", etc.
        idxs = [i for i, m in enumerate(models) if m == model]
        xs = [times[i] for i in idxs]
        ys = [costs[i] for i in idxs]
        alphas = [0.3 if concurrent[i] else 1.0 for i in idxs]
        for x, y, a in zip(xs, ys, alphas):
            ax.scatter(x, y, color=color, alpha=a, s=60, zorder=3)
        # Legend entry (one per model)
        ax.scatter([], [], color=color, label=label, s=60)

    ax.set_ylabel("% 5h за 1K output tokens")
    ax.set_title(f"Удельная стоимость токенов — {year_month}")
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()

    out_path = str(self._output_dir / f"cost_{year_month}.png")
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    return out_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_charts.py -v`
Expected: all tests PASS (old + new). Existing tests that create `UsageCharts(collector=..., output_dir=...)` still work because `cost_tracker` defaults to `None`.

- [ ] **Step 5: Commit**

```bash
git add analytics/charts.py tests/test_charts.py
git commit -m "feat: add token cost scatter chart"
```

---

### Task 8: Telegram UI — Cost Chart Button

**Files:**
- Modify: `analytics/handlers.py`

- [ ] **Step 1: Add callback constant and handler**

In `analytics/handlers.py`:

1. Add constant:
```python
CB_CHART_COST = "chart_cost"
```

2. Add button to the keyboard in `show_limits` (first row):
```python
keyboard = [
    [
        InlineKeyboardButton("📈 День", callback_data=CB_CHART_DAY),
        InlineKeyboardButton("📈 Неделя", callback_data=CB_CHART_WEEK),
        InlineKeyboardButton("🗓 Heatmap", callback_data=CB_CHART_HEATMAP),
    ],
    [InlineKeyboardButton("💰 Стоимость", callback_data=CB_CHART_COST)],
    [InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)],
]
```

3. Add button to `_chart_kb`:
```python
_chart_kb = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📈 День", callback_data=CB_CHART_DAY),
        InlineKeyboardButton("📈 Неделя", callback_data=CB_CHART_WEEK),
        InlineKeyboardButton("🗓 Heatmap", callback_data=CB_CHART_HEATMAP),
    ],
    [InlineKeyboardButton("💰 Стоимость", callback_data=CB_CHART_COST)],
    [InlineKeyboardButton("📊 К лимитам", callback_data=CB_LIMITS)],
])
```

4. Add handler function inside `create_analytics_handlers`:
```python
@auth_check
async def chart_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await _send_chart(update, charts.generate_token_cost(today), f"💰 Стоимость токенов — {today[:7]}")
```

5. Add to return list:
```python
CallbackQueryHandler(chart_cost, pattern=f"^{CB_CHART_COST}$"),
```

- [ ] **Step 2: Pass cost_tracker to UsageCharts in bot.py**

In `bot.py`, update the `charts` line:
```python
charts = UsageCharts(collector=collector, output_dir="data/charts", cost_tracker=cost_tracker)
```

- [ ] **Step 3: Verify bot starts**

Run: `python -c "from bot import main; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add analytics/handlers.py bot.py
git commit -m "feat: add token cost chart button to Telegram UI"
```

---

### Task 9: Cost Warning Stub in Notifier

**Files:**
- Modify: `core/notifier.py`
- Modify: `tests/test_notifier.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_notifier.py`:

```python
@pytest.mark.asyncio
async def test_cost_warning(notifier):
    await notifier.cost_warning(
        project="test-proj", cost_per_1k=0.05, period="5h"
    )
    notifier._bot.send_message.assert_called_once()
    text = notifier._bot.send_message.call_args.kwargs["text"]
    assert "test-proj" in text
    assert "5h" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_notifier.py::test_cost_warning -v`
Expected: FAIL — `Notifier has no attribute 'cost_warning'`

- [ ] **Step 3: Implement stub**

In `core/notifier.py`, add method:

```python
async def cost_warning(
    self, project: str, cost_per_1k: float, period: str
) -> None:
    await self.send(
        f"💰 <b>{project}</b>: высокая стоимость токенов\n"
        f"{period}: {cost_per_1k:.3f}% за 1K output",
        reply_markup=_MENU_KB,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_notifier.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/notifier.py tests/test_notifier.py
git commit -m "feat: add cost_warning stub to notifier"
```

---

### Task 10: Remove Temporary Payload Logging from HookServer

**Files:**
- Modify: `core/hook_server.py`

- [ ] **Step 1: Clean up temporary debug logging**

In `core/hook_server.py`, revert the payload logging added during brainstorming:

Replace:
```python
        logger.info("Hook event: %s | Payload keys: %s", event, list(data.keys()))
        if event == "Stop":
            logger.info("Stop payload: %s", json.dumps(data, default=str)[:5000])
```

With:
```python
        logger.info("Hook event: %s", event)
```

Keep the `import json` — it's now used by the cost recording code added in Task 5.

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -v`
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add core/hook_server.py
git commit -m "chore: remove temporary payload logging from hook server"
```

---

### Task 11: Full Integration Test

**Files:**
- All

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: all tests PASS

- [ ] **Step 2: Verify CSV directory structure**

Run: `python -c "from core.cost_tracker import CostTracker; CostTracker(); print('data/costs/ created OK')"`
Expected: `data/costs/ created OK`

- [ ] **Step 3: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "fix: integration fixups for token cost tracking"
```

Skip this step if no changes are needed.
