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
