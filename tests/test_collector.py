import pytest
from pathlib import Path

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
