import pytest
from unittest.mock import AsyncMock, MagicMock

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
