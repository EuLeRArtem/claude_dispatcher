import asyncio
import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import aiohttp

from core.notifier import Notifier

logger = logging.getLogger(__name__)

MESSAGES_URL = "https://api.anthropic.com/v1/messages"
_BACKOFF_FILE = Path("data/.usage_backoff")

# Minimal ping to read rate-limit headers (cheapest possible call)
_PING_PAYLOAD = {
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 1,
    "messages": [{"role": "user", "content": "."}],
}

# Fallbacks if auto-detection fails
_DEFAULT_BETA = "oauth-2025-04-20"
_DEFAULT_VERSION = "2.1.87"


def _detect_claude_code_info() -> tuple[str, str]:
    """Extract anthropic-beta header and version from installed Claude Code.

    Returns (anthropic_beta, version) with fallbacks if detection fails.
    """
    beta = _DEFAULT_BETA
    version = _DEFAULT_VERSION

    try:
        # Find Claude Code install dir via npm
        result = subprocess.run(
            ["npm", "root", "-g"], capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return beta, version

        pkg_dir = Path(result.stdout.strip()) / "@anthropic-ai" / "claude-code"
        if not pkg_dir.exists():
            return beta, version

        # Version from package.json
        pkg_json = pkg_dir / "package.json"
        if pkg_json.exists():
            version = json.loads(pkg_json.read_text(encoding="utf-8")).get("version", version)

        # anthropic-beta from cli.js (pattern: SX="oauth-YYYY-MM-DD")
        cli_js = pkg_dir / "cli.js"
        if cli_js.exists():
            # Read first 5MB — bundled file is ~13MB, constant position may shift
            with open(cli_js, "r", encoding="utf-8") as f:
                chunk = f.read(5_000_000)
            m = re.search(r'SX="(oauth-\d{4}-\d{2}-\d{2})"', chunk)
            if m:
                beta = m.group(1)

    except Exception:
        logger.debug("Failed to detect Claude Code info, using defaults", exc_info=True)

    logger.info("Claude Code: version=%s, anthropic-beta=%s", version, beta)
    return beta, version


ANTHROPIC_BETA, CLAUDE_CODE_VERSION = _detect_claude_code_info()


@dataclass
class UsageData:
    five_hour_util: float = 0.0
    five_hour_resets_at: str = ""
    seven_day_util: float = 0.0
    seven_day_resets_at: str = ""
    seven_day_sonnet_util: float = 0.0
    timestamp: str = ""


def parse_usage_headers(headers) -> UsageData:
    """Extract rate-limit utilization from /v1/messages response headers.

    Headers use 0.0-1.0 scale; reset values are Unix timestamps.
    """
    five_h_util = float(headers.get("anthropic-ratelimit-unified-5h-utilization", 0))
    seven_d_util = float(headers.get("anthropic-ratelimit-unified-7d-utilization", 0))

    five_h_resets_at = ""
    raw = headers.get("anthropic-ratelimit-unified-5h-reset", "")
    if raw:
        five_h_resets_at = datetime.fromtimestamp(float(raw), tz=timezone.utc).isoformat()

    seven_d_resets_at = ""
    raw = headers.get("anthropic-ratelimit-unified-7d-reset", "")
    if raw:
        seven_d_resets_at = datetime.fromtimestamp(float(raw), tz=timezone.utc).isoformat()

    return UsageData(
        five_hour_util=five_h_util,
        five_hour_resets_at=five_h_resets_at,
        seven_day_util=seven_d_util,
        seven_day_resets_at=seven_d_resets_at,
        seven_day_sonnet_util=0.0,  # not available in response headers
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


class LimitTracker:
    _MIN_BACKOFF = 60
    _MAX_BACKOFF = 900  # 15 minutes

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
        self._backoff_seconds: int = self._load_backoff()
        self._consecutive_429: int = 0
        self.latest: UsageData | None = None

    @staticmethod
    def _load_backoff() -> int:
        """Load remaining backoff from file (survives restarts)."""
        try:
            if _BACKOFF_FILE.exists():
                data = json.loads(_BACKOFF_FILE.read_text())
                resume_at = data.get("resume_at", 0)
                remaining = int(resume_at - datetime.now(timezone.utc).timestamp())
                if remaining > 0:
                    logger.info("Resuming rate-limit backoff: %ds remaining", remaining)
                    return remaining
                _BACKOFF_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        return 0

    @staticmethod
    def _save_backoff(seconds: int) -> None:
        """Persist backoff so restarts don't reset it."""
        try:
            _BACKOFF_FILE.parent.mkdir(parents=True, exist_ok=True)
            resume_at = datetime.now(timezone.utc).timestamp() + seconds
            _BACKOFF_FILE.write_text(json.dumps({"resume_at": resume_at}))
        except Exception:
            pass

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
                    "anthropic-version": "2023-06-01",
                    "anthropic-beta": ANTHROPIC_BETA,
                    "User-Agent": f"claude-code/{CLAUDE_CODE_VERSION}",
                }
                async with session.post(
                    MESSAGES_URL, headers=headers, json=_PING_PAYLOAD,
                ) as resp:
                    if resp.status == 429:
                        self._consecutive_429 += 1
                        raw_retry = int(resp.headers.get("retry-after", 0))
                        exp_backoff = min(
                            self._MIN_BACKOFF * (2 ** (self._consecutive_429 - 1)),
                            self._MAX_BACKOFF,
                        )
                        retry_after = max(raw_retry, exp_backoff)
                        logger.warning(
                            "Rate limited (attempt %d), retry in %ds (header=%ds)",
                            self._consecutive_429, retry_after, raw_retry,
                        )
                        self._backoff_seconds = retry_after
                        self._save_backoff(retry_after)
                        return None
                    if resp.status not in (200, 201):
                        body = await resp.text()
                        logger.warning("Messages API ping returned %d: %s", resp.status, body[:500])
                        return None
                    await resp.read()
                    _BACKOFF_FILE.unlink(missing_ok=True)
                    self._consecutive_429 = 0
                    usage = parse_usage_headers(resp.headers)
                    logger.info(
                        "Usage: 5h=%.0f%% 7d=%.0f%%",
                        usage.five_hour_util * 100,
                        usage.seven_day_util * 100,
                    )
                    return usage
        except Exception:
            logger.exception("Failed to poll usage via messages ping")
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
            if self._backoff_seconds > 0:
                await asyncio.sleep(self._backoff_seconds)
                self._backoff_seconds = 0
                continue
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
