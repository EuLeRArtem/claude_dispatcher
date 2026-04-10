import pytest
from pathlib import Path

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
