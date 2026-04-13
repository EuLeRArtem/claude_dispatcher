import pytest
from unittest.mock import AsyncMock, MagicMock

from core.notifier import Notifier
from core.notification_settings import NotificationSettings


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
        chat_id=123, text="Hello test", parse_mode="HTML", reply_markup=None,
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


@pytest.mark.asyncio
async def test_permission_needed(notifier, bot):
    await notifier.permission_needed(
        project="myproject",
        url="https://claude.ai/code/session_abc",
        message="Claude needs permission to use Bash",
    )
    bot.send_message.assert_called_once()
    text = bot.send_message.call_args.kwargs["text"]
    assert "myproject" in text
    # URL goes into reply_markup button, not text
    markup = bot.send_message.call_args.kwargs["reply_markup"]
    urls = [btn.url for row in markup.inline_keyboard for btn in row if btn.url]
    assert any("session_abc" in u for u in urls)


@pytest.mark.asyncio
async def test_permission_needed_no_url(notifier, bot):
    await notifier.permission_needed(project="proj", url=None, message="needs perm")
    text = bot.send_message.call_args.kwargs["text"]
    assert "proj" in text


@pytest.mark.asyncio
async def test_agent_idle(notifier, bot):
    await notifier.agent_idle(project="proj", url="https://claude.ai/code/session_x")
    text = bot.send_message.call_args.kwargs["text"]
    assert "proj" in text


@pytest.mark.asyncio
async def test_agent_stopped(notifier, bot):
    await notifier.agent_stopped(project="proj", error="rate_limit", details="retry 60s")
    text = bot.send_message.call_args.kwargs["text"]
    assert "rate_limit" in text


@pytest.mark.asyncio
async def test_cost_warning(notifier, bot):
    await notifier.cost_warning(
        project="test-proj", cost_per_1k=0.05, period="5h"
    )
    bot.send_message.assert_called_once()
    text = bot.send_message.call_args.kwargs["text"]
    assert "test-proj" in text
    assert "5h" in text


# --- Notification settings filtering ---

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
