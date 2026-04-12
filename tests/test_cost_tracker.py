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
