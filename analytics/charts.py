import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

from analytics.collector import UsageCollector

logger = logging.getLogger(__name__)

_MODEL_COLORS = {
    "claude-opus-4-6": "#7C3AED",
    "claude-sonnet-4-6": "#2563EB",
    "claude-haiku-4-5-20251001": "#10B981",
}
_DEFAULT_COLOR = "#6B7280"


class UsageCharts:
    def __init__(self, collector: UsageCollector, output_dir: str = "data/charts", cost_tracker=None):
        self._collector = collector
        self._cost_tracker = cost_tracker
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def _filter_rows(self, rows: list[dict], start: datetime, end: datetime) -> list[dict]:
        result = []
        for row in rows:
            dt = datetime.fromisoformat(row["timestamp"])
            if start <= dt < end:
                result.append(row)
        return result

    def generate_day(self, date_str: str) -> str | None:
        """Generate chart for a single day. date_str format: YYYY-MM-DD"""
        year_month = date_str[:7]
        rows = self._collector.load(year_month)
        day_start = datetime.fromisoformat(f"{date_str}T00:00:00+00:00")
        day_end = day_start + timedelta(days=1)
        day_rows = self._filter_rows(rows, day_start, day_end)

        if not day_rows:
            return None

        times = [datetime.fromisoformat(r["timestamp"]) for r in day_rows]
        five_h = [float(r["five_hour_util"]) * 100 for r in day_rows]
        seven_d = [float(r["seven_day_util"]) * 100 for r in day_rows]

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(times, five_h, label="5h limit", linewidth=2)
        ax.plot(times, seven_d, label="7d limit", linewidth=2)
        ax.set_ylabel("Usage %")
        ax.set_title(f"Usage — {date_str}")
        ax.legend()
        ax.set_ylim(0, 100)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        out_path = str(self._output_dir / f"day_{date_str}.png")
        fig.savefig(out_path, dpi=100)
        plt.close(fig)
        return out_path

    def generate_week(self, date_str: str) -> str | None:
        """Generate chart for 7 days ending on date_str."""
        end = datetime.fromisoformat(f"{date_str}T23:59:59+00:00")
        start = end - timedelta(days=7)

        all_rows = []
        # May span two months
        for month_offset in range(2):
            dt = start + timedelta(days=month_offset * 28)
            ym = dt.strftime("%Y-%m")
            all_rows.extend(self._collector.load(ym))

        week_rows = self._filter_rows(all_rows, start, end + timedelta(seconds=1))
        if not week_rows:
            return None

        times = [datetime.fromisoformat(r["timestamp"]) for r in week_rows]
        five_h = [float(r["five_hour_util"]) * 100 for r in week_rows]
        seven_d = [float(r["seven_day_util"]) * 100 for r in week_rows]

        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(times, five_h, label="5h limit", linewidth=1.5)
        ax.plot(times, seven_d, label="7d limit", linewidth=1.5)
        ax.set_ylabel("Usage %")
        ax.set_title(f"Usage — week ending {date_str}")
        ax.legend()
        ax.set_ylim(0, 100)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        out_path = str(self._output_dir / f"week_{date_str}.png")
        fig.savefig(out_path, dpi=100)
        plt.close(fig)
        return out_path

    def generate_heatmap(self, year_month: str) -> str | None:
        """Generate heatmap: hours (x) vs weekdays (y) for five_hour_util."""
        rows = self._collector.load(year_month)
        if not rows:
            return None

        # Aggregate: weekday x hour -> list of values
        grid = defaultdict(list)
        for row in rows:
            dt = datetime.fromisoformat(row["timestamp"])
            grid[(dt.weekday(), dt.hour)].append(float(row["five_hour_util"]) * 100)

        # Build 7x24 matrix (Mon=0 .. Sun=6)
        matrix = np.full((7, 24), float("nan"))
        for (wd, h), vals in grid.items():
            matrix[wd][h] = sum(vals) / len(vals)

        fig, ax = plt.subplots(figsize=(12, 4))
        im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=100)
        ax.set_yticks(range(7))
        ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        ax.set_xticks(range(24))
        ax.set_xticklabels([f"{h:02d}" for h in range(24)])
        ax.set_xlabel("Hour (UTC)")
        ax.set_title(f"5h Usage Heatmap — {year_month}")
        fig.colorbar(im, ax=ax, label="Usage %")
        fig.tight_layout()

        out_path = str(self._output_dir / f"heatmap_{year_month}.png")
        fig.savefig(out_path, dpi=100)
        plt.close(fig)
        return out_path

    def generate_token_cost(self, date_str: str) -> str | None:
        """Generate scatter plot: unit cost (% per 1K output tokens) over time."""
        if not self._cost_tracker:
            return None

        year_month = date_str[:7]
        rows = self._cost_tracker.load(year_month)

        # Filter: need numeric delta_5h and output_tokens > 0
        valid = []
        for row in rows:
            try:
                delta = float(row["delta_5h"])
                out_tokens = int(row["output_tokens"])
                if out_tokens <= 0:
                    continue
                valid.append(row)
            except (ValueError, KeyError):
                continue

        if not valid:
            return None

        times = [datetime.fromisoformat(r["timestamp"]) for r in valid]
        costs = [float(r["delta_5h"]) / int(r["output_tokens"]) * 1000 * 100 for r in valid]
        models = [r.get("model", "unknown") for r in valid]
        concurrent = [r.get("concurrent", "False") == "True" for r in valid]

        fig, ax = plt.subplots(figsize=(10, 5))

        for model in set(models):
            color = _MODEL_COLORS.get(model, _DEFAULT_COLOR)
            label = model.split("-")[1] if "-" in model else model
            idxs = [i for i, m in enumerate(models) if m == model]
            xs = [times[i] for i in idxs]
            ys = [costs[i] for i in idxs]
            alphas = [0.3 if concurrent[i] else 1.0 for i in idxs]
            for x, y, a in zip(xs, ys, alphas):
                ax.scatter(x, y, color=color, alpha=a, s=60, zorder=3)
            ax.scatter([], [], color=color, label=label, s=60)

        ax.set_ylabel("% 5h за 1K output tokens")
        ax.set_title(f"Удельная стоимость токенов — {year_month}")
        ax.legend()
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        fig.tight_layout()

        out_path = str(self._output_dir / f"cost_{year_month}.png")
        fig.savefig(out_path, dpi=100)
        plt.close(fig)
        return out_path
