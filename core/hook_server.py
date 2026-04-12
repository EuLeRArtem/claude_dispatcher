import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

from core.cost_tracker import CostTracker, SessionCost
from core.notifier import Notifier
from core.transcript_parser import parse_transcript

logger = logging.getLogger(__name__)


class HookServer:
    def __init__(self, notifier: Notifier, session_manager, port: int = 9384,
                 cost_tracker: CostTracker | None = None, limit_tracker=None):
        self._notifier = notifier
        self._session_manager = session_manager
        self._port = port
        self._cost_tracker = cost_tracker
        self._limit_tracker = limit_tracker
        self._runner: web.AppRunner | None = None

    def create_app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/hooks", self._handle_hook)
        return app

    async def start(self) -> None:
        app = self.create_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self._port)
        await site.start()
        logger.info("Hook server listening on 127.0.0.1:%d", self._port)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    def _find_session_by_cwd(self, cwd: str):
        """Find a bot session whose project path matches the hook's cwd."""
        for info in self._session_manager.list_sessions():
            return info
        return None

    def _get_context(self, data: dict) -> tuple[str, str | None]:
        """Extract project name and URL from hook data + session lookup."""
        cwd = data.get("cwd", "")
        session = self._find_session_by_cwd(cwd)
        if session:
            return session.project_name, session.url
        return Path(cwd).name if cwd else "unknown", None

    async def _record_session_cost(self, data: dict, project: str, session) -> None:
        """Parse transcript, poll utilization, compute delta, record cost."""
        transcript_path = data.get("transcript_path")
        if not transcript_path or not self._cost_tracker:
            return

        usage = parse_transcript(transcript_path)
        if not usage:
            logger.warning("Could not parse transcript: %s", transcript_path)
            return

        # Poll current utilization
        util_after = None
        if self._limit_tracker:
            util_after = await self._limit_tracker.poll_once()

        # Get snapshot from session
        util_before = session.util_snapshot if session else None

        # Compute deltas
        if util_before and util_after:
            delta_5h = util_after.five_hour_util - util_before.five_hour_util
            delta_7d = util_after.seven_day_util - util_before.seven_day_util
            before_5h = util_before.five_hour_util
            before_7d = util_before.seven_day_util
            after_5h = util_after.five_hour_util
            after_7d = util_after.seven_day_util
        else:
            delta_5h = ""
            delta_7d = ""
            before_5h = util_before.five_hour_util if util_before else ""
            before_7d = util_before.seven_day_util if util_before else ""
            after_5h = util_after.five_hour_util if util_after else ""
            after_7d = util_after.seven_day_util if util_after else ""

        active_sessions = self._session_manager.list_sessions()
        concurrent = len(active_sessions) > 1

        duration_min = session.duration_minutes() if session else 0

        cost = SessionCost(
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session.session_id if session else data.get("session_id", ""),
            project=project,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens,
            cache_creation_tokens=usage.cache_creation_input_tokens,
            request_count=usage.request_count,
            util_before_5h=before_5h,
            util_after_5h=after_5h,
            util_before_7d=before_7d,
            util_after_7d=after_7d,
            delta_5h=delta_5h,
            delta_7d=delta_7d,
            concurrent=concurrent,
            duration_min=duration_min,
        )
        self._cost_tracker.record(cost)
        logger.info(
            "Recorded session cost: %s %s Δ5h=%.2f%% Δ7d=%.2f%%",
            project, usage.model,
            delta_5h * 100 if isinstance(delta_5h, float) else 0,
            delta_7d * 100 if isinstance(delta_7d, float) else 0,
        )

    async def _handle_hook(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.Response(status=400, text="invalid json")

        event = data.get("hook_event_name", "")
        logger.info("Hook event: %s", event)

        project, url = self._get_context(data)

        if event == "Stop":
            last_msg = data.get("last_assistant_message", "")
            truncated = last_msg[:300] + "..." if len(last_msg) > 300 else last_msg
            from core.notifier import _MENU_KB
            await self._notifier.send(
                f"✅ <b>{project}</b>: задача завершена\n<pre>{truncated}</pre>",
                reply_markup=_MENU_KB,
            )
            # Record session cost
            session = self._find_session_by_cwd(data.get("cwd", ""))
            await self._record_session_cost(data, project, session)

        elif event == "Notification":
            ntype = data.get("notification_type", "")
            message = data.get("message", "")

            if ntype == "permission_prompt":
                await self._notifier.permission_needed(
                    project=project, url=url, message=message
                )
            elif ntype == "idle_prompt":
                await self._notifier.agent_idle(project=project, url=url)
            else:
                logger.debug("Ignoring notification type: %s", ntype)

        elif event == "StopFailure":
            error = data.get("error", "unknown")
            details = data.get("error_details", "")
            await self._notifier.agent_stopped(
                project=project, error=error, details=details
            )

        else:
            logger.debug("Ignoring hook event: %s", event)

        return web.Response(status=200)
