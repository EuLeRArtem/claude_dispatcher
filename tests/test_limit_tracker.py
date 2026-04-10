import pytest
from unittest.mock import AsyncMock

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
    assert 70 not in triggered2


def test_threshold_resets_when_utilization_drops(notifier):
    tracker = LimitTracker(
        notifier=notifier,
        thresholds=[70, 85, 95],
        poll_interval_sec=60,
        credentials_path="dummy",
    )
    tracker._check_thresholds("5h", 0.72)
    tracker._check_thresholds("5h", 0.10)
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
