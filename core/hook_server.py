import logging
from pathlib import Path

from aiohttp import web

from core.notifier import Notifier

logger = logging.getLogger(__name__)


class HookServer:
    def __init__(self, notifier: Notifier, session_manager, port: int = 9384):
        self._notifier = notifier
        self._session_manager = session_manager
        self._port = port
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
            await self._notifier.send(
                f"✅ <b>{project}</b>: задача завершена\n<pre>{truncated}</pre>"
            )

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
