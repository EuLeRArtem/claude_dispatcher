import pytest
from unittest.mock import AsyncMock

from core.limit_tracker import LimitTracker, UsageData, parse_usage_headers


SAMPLE_HEADERS = {
    "anthropic-ratelimit-unified-5h-utilization": "0.72",
    "anthropic-ratelimit-unified-7d-utilization": "0.12",
    "anthropic-ratelimit-unified-5h-reset": "1744311600",
    "anthropic-ratelimit-unified-7d-reset": "1744657200",
}


def test_parse_usage_headers():
    data = parse_usage_headers(SAMPLE_HEADERS)
    assert data.five_hour_util == pytest.approx(0.72)
    assert data.seven_day_util == pytest.approx(0.12)
    assert data.seven_day_sonnet_util == 0.0
    assert data.five_hour_resets_at != ""
    assert data.seven_day_resets_at != ""


def test_parse_usage_headers_missing():
    data = parse_usage_headers({})
    assert data.five_hour_util == 0.0
    assert data.seven_day_util == 0.0
    assert data.seven_day_sonnet_util == 0.0
    assert data.five_hour_resets_at == ""
    assert data.seven_day_resets_at == ""


def test_parse_usage_headers_partial():
    data = parse_usage_headers({
        "anthropic-ratelimit-unified-5h-utilization": "0.5",
    })
    assert data.five_hour_util == 0.5
    assert data.seven_day_util == 0.0


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
