import pytest
from pathlib import Path
from unittest.mock import MagicMock

from analytics.collector import UsageCollector
from analytics.charts import UsageCharts
from core.limit_tracker import UsageData


@pytest.fixture
def collector(tmp_path):
    c = UsageCollector(data_dir=str(tmp_path))
    # Add 48 hours of data (every 30 min)
    for day in [10, 11]:
        for hour in range(24):
            for minute in [0, 30]:
                c.record(UsageData(
                    five_hour_util=0.3 + (hour / 100),
                    seven_day_util=0.1,
                    seven_day_sonnet_util=0.05,
                    timestamp=f"2026-04-{day:02d}T{hour:02d}:{minute:02d}:00+00:00",
                ))
    return c


@pytest.fixture
def charts(collector, tmp_path):
    return UsageCharts(collector=collector, output_dir=str(tmp_path / "charts"))


def test_generate_day_chart(charts):
    path = charts.generate_day("2026-04-10")
    assert Path(path).exists()
    assert path.endswith(".png")


def test_generate_week_chart(charts):
    path = charts.generate_week("2026-04-10")
    assert Path(path).exists()
    assert path.endswith(".png")


def test_generate_heatmap(charts):
    path = charts.generate_heatmap("2026-04")
    assert Path(path).exists()
    assert path.endswith(".png")


def test_generate_day_no_data(charts):
    path = charts.generate_day("2099-01-01")
    assert path is None


def test_generate_token_cost_returns_path(tmp_path):
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
