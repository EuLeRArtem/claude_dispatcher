import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.hook_server import HookServer
from core.limit_tracker import UsageData


@pytest.fixture
def notifier():
    n = MagicMock()
    n.permission_needed = AsyncMock()
    n.agent_idle = AsyncMock()
    n.agent_stopped = AsyncMock()
    n.session_finished = AsyncMock()
    n.send = AsyncMock()
    n.task_completed = AsyncMock()
    return n


@pytest.fixture
def session_manager():
    sm = MagicMock()
    sm.list_sessions = MagicMock(return_value=[])
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
    notifier.task_completed.assert_called_once()
    text = notifier.task_completed.call_args[1]["summary"]
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
    session_manager.list_sessions.return_value = [session_info]

    cl = await client
    resp = await cl.post("/hooks", json={
        "hook_event_name": "Notification",
        "notification_type": "permission_prompt",
        "session_id": "claude-internal-id",
        "cwd": "/tmp/proj",
        "message": "Needs permission",
    })
    assert resp.status == 200
    notifier.permission_needed.assert_called_once_with(
        project="my-project", url="https://claude.ai/code/session_xyz", message="Needs permission"
    )


# --- Cost tracking tests ---

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
    notifier.task_completed.assert_called_once()
    # No transcript_path → no cost record
    cost_tracker.record.assert_not_called()
