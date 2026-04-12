import csv
import logging
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

FIELDNAMES = [
    "timestamp", "session_id", "project", "model",
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens",
    "request_count",
    "util_before_5h", "util_after_5h", "util_before_7d", "util_after_7d",
    "delta_5h", "delta_7d",
    "concurrent", "duration_min",
]


@dataclass
class SessionCost:
    timestamp: str
    session_id: str
    project: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    request_count: int
    util_before_5h: float | str  # "" when snapshot failed
    util_after_5h: float | str
    util_before_7d: float | str
    util_after_7d: float | str
    delta_5h: float | str
    delta_7d: float | str
    concurrent: bool
    duration_min: int


class CostTracker:
    def __init__(self, data_dir: str = "data/costs"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _csv_path(self, timestamp: str) -> Path:
        dt = datetime.fromisoformat(timestamp)
        return self._data_dir / f"{dt.strftime('%Y-%m')}.csv"

    def record(self, cost: SessionCost) -> None:
        csv_path = self._csv_path(cost.timestamp)
        file_exists = csv_path.exists()
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow({field.name: getattr(cost, field.name) for field in fields(cost)})

    def load(self, year_month: str) -> list[dict]:
        csv_path = self._data_dir / f"{year_month}.csv"
        if not csv_path.exists():
            return []
        with open(csv_path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
