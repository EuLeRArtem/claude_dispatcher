import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import aiohttp

from core.notifier import Notifier

logger = logging.getLogger(__name__)

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"


@dataclass
class UsageData:
    five_hour_util: float = 0.0
    five_hour_resets_at: str = ""
    seven_day_util: float = 0.0
    seven_day_resets_at: str = ""
    seven_day_sonnet_util: float = 0.0
    timestamp: str = ""


def parse_usage_response(data: dict) -> UsageData:
    five_hour = data.get("five_hour", {})
    seven_day = data.get("seven_day", {})
    seven_day_sonnet = data.get("seven_day_sonnet", {})
    return UsageData(
        five_hour_util=five_hour.get("utilization", 0.0),
        five_hour_resets_at=five_hour.get("resets_at", ""),
        seven_day_util=seven_day.get("utilization", 0.0),
        seven_day_resets_at=seven_day.get("resets_at", ""),
        seven_day_sonnet_util=seven_day_sonnet.get("utilization", 0.0),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


class LimitTracker:
    def __init__(
        self,
        notifier: Notifier,
        thresholds: list[int],
        poll_interval_sec: int,
        credentials_path: str,
        on_usage: Callable[[UsageData], None] | None = None,
    ):
        self._notifier = notifier
        self._thresholds = sorted(thresholds)
        self._poll_interval = poll_interval_sec
        self._credentials_path = credentials_path
        self._on_usage = on_usage
        self._fired: dict[str, set[int]] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self.latest: UsageData | None = None

    def _get_token(self) -> str | None:
        try:
            with open(self._credentials_path, "r", encoding="utf-8") as f:
                creds = json.load(f)
            return creds.get("claudeAiOauth", {}).get("accessToken")
        except Exception:
            logger.exception("Failed to read credentials")
            return None

    def _check_thresholds(self, period: str, utilization: float) -> set[int]:
        percent = utilization * 100
        if period not in self._fired:
            self._fired[period] = set()

        # Reset fired thresholds if utilization dropped below them
        to_reset = {t for t in self._fired[period] if percent < t}
        self._fired[period] -= to_reset

        triggered = set()
        for threshold in self._thresholds:
            if percent >= threshold and threshold not in self._fired[period]:
                triggered.add(threshold)
                self._fired[period].add(threshold)

        return triggered

    async def _poll_once(self) -> UsageData | None:
        token = self._get_token()
        if not token:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
                async with session.get(USAGE_URL, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning("Usage API returned %d", resp.status)
                        return None
                    data = await resp.json()
                    return parse_usage_response(data)
        except Exception:
            logger.exception("Failed to poll usage API")
            return None

    async def _notify_thresholds(self, usage: UsageData) -> None:
        for period, util, resets_at in [
            ("5h", usage.five_hour_util, usage.five_hour_resets_at),
            ("7d", usage.seven_day_util, usage.seven_day_resets_at),
        ]:
            triggered = self._check_thresholds(period, util)
            for threshold in sorted(triggered):
                reset_min = 0
                if resets_at:
                    try:
                        reset_dt = datetime.fromisoformat(resets_at)
                        delta = reset_dt - datetime.now(timezone.utc)
                        reset_min = max(0, int(delta.total_seconds() / 60))
                    except ValueError:
                        pass
                await self._notifier.limit_warning(
                    period=period, percent=threshold, reset_minutes=reset_min
                )

    async def _poll_loop(self) -> None:
        while self._running:
            usage = await self._poll_once()
            if usage:
                self.latest = usage
                await self._notify_thresholds(usage)
                if self._on_usage:
                    self._on_usage(usage)
            await asyncio.sleep(self._poll_interval)

    def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
