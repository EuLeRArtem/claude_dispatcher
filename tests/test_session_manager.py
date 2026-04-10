import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

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
        started_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        process=MagicMock(),
    )
    assert isinstance(info.duration_minutes(), int)
