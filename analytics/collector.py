import csv
import logging
from datetime import datetime
from pathlib import Path

from core.limit_tracker import UsageData

logger = logging.getLogger(__name__)

FIELDNAMES = ["timestamp", "five_hour_util", "seven_day_util", "seven_day_sonnet_util"]


class UsageCollector:
    def __init__(self, data_dir: str = "data/usage"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _csv_path(self, timestamp: str) -> Path:
        dt = datetime.fromisoformat(timestamp)
        filename = dt.strftime("%Y-%m") + ".csv"
        return self._data_dir / filename

    def record(self, usage: UsageData) -> None:
        csv_path = self._csv_path(usage.timestamp)
        file_exists = csv_path.exists()

        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow({
                "timestamp": usage.timestamp,
                "five_hour_util": usage.five_hour_util,
                "seven_day_util": usage.seven_day_util,
                "seven_day_sonnet_util": usage.seven_day_sonnet_util,
            })

    def load(self, year_month: str) -> list[dict]:
        csv_path = self._data_dir / f"{year_month}.csv"
        if not csv_path.exists():
            return []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
