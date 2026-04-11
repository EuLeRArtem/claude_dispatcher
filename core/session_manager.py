import asyncio
import logging
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from core.notifier import Notifier

logger = logging.getLogger(__name__)

_REMOTE_URL_RE = re.compile(r"(https://claude\.ai/code/session_\S+)")
_IS_WINDOWS = sys.platform == "win32"


def _find_claude() -> str:
    """Find claude executable. On Windows, prefer .cmd wrapper."""
    if _IS_WINDOWS:
        cmd_path = shutil.which("claude.cmd") or shutil.which("claude")
        if cmd_path:
            return cmd_path
    return shutil.which("claude") or "claude"


async def _create_process(cmd: list[str], cwd: str) -> asyncio.subprocess.Process:
    """Create subprocess, handling Windows .cmd files."""
    if _IS_WINDOWS:
        # On Windows, .cmd files need shell=True; use list2cmdline for proper quoting
        shell_cmd = subprocess.list2cmdline(cmd)
        return await asyncio.create_subprocess_shell(
            shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
    return await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )


def parse_remote_url(text: str) -> str | None:
    match = _REMOTE_URL_RE.search(text)
    return match.group(1) if match else None


@dataclass
class SessionInfo:
    session_id: str
    project_name: str
    mode: str  # "remote" or "normal"
    started_at: datetime
    process: asyncio.subprocess.Process
    url: str | None = None

    def duration_minutes(self) -> int:
        delta = datetime.now(timezone.utc) - self.started_at
        return int(delta.total_seconds() / 60)


class SessionManager:
    def __init__(self, notifier: Notifier):
        self._notifier = notifier
        self._sessions: dict[str, SessionInfo] = {}

    def list_sessions(self) -> list[SessionInfo]:
        return list(self._sessions.values())

    def get_session(self, session_id: str) -> SessionInfo | None:
        return self._sessions.get(session_id)

    async def start_remote(self, project_name: str, project_path: str, prompt: str = "") -> SessionInfo:
        claude = _find_claude()
        cmd = [claude, "--remote-control"]
        if prompt:
            cmd.append(prompt)

        process = await _create_process(cmd, cwd=project_path)

        session_id = str(uuid.uuid4())[:8]
        info = SessionInfo(
            session_id=session_id,
            project_name=project_name,
            mode="remote",
            started_at=datetime.now(timezone.utc),
            process=process,
        )
        self._sessions[session_id] = info

        # Read stdout in background to find URL
        asyncio.create_task(self._read_remote_output(info))
        # Monitor process lifecycle
        asyncio.create_task(self._monitor_process(info))

        return info

    async def start_normal(self, project_name: str, project_path: str, prompt: str) -> SessionInfo:
        claude = _find_claude()
        cmd = [claude, "-p", "--output-format", "json", prompt]

        process = await _create_process(cmd, cwd=project_path)

        session_id = str(uuid.uuid4())[:8]
        info = SessionInfo(
            session_id=session_id,
            project_name=project_name,
            mode="normal",
            started_at=datetime.now(timezone.utc),
            process=process,
        )
        self._sessions[session_id] = info

        await self._notifier.session_started(project=project_name, mode="normal")
        # Monitor process lifecycle
        asyncio.create_task(self._monitor_process(info))

        return info

    async def kill_session(self, session_id: str) -> bool:
        info = self._sessions.get(session_id)
        if not info:
            return False

        info.process.terminate()
        try:
            await asyncio.wait_for(info.process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            info.process.kill()
            await info.process.wait()

        self._sessions.pop(session_id, None)
        return True

    async def _read_remote_output(self, info: SessionInfo) -> None:
        collected = ""
        try:
            while True:
                chunk = await info.process.stdout.read(4096)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                collected += text
                url = parse_remote_url(collected)
                if url:
                    info.url = url
                    await self._notifier.session_started(
                        project=info.project_name, mode="remote", url=url
                    )
                    break
            # Continue draining stdout
            while True:
                chunk = await info.process.stdout.read(4096)
                if not chunk:
                    break
        except Exception:
            logger.exception("Error reading remote output for %s", info.project_name)

    async def _monitor_process(self, info: SessionInfo) -> None:
        returncode = await info.process.wait()
        duration = info.duration_minutes()
        self._sessions.pop(info.session_id, None)

        if returncode == 0:
            await self._notifier.session_finished(
                project=info.project_name, duration_min=duration
            )
        else:
            stderr_bytes = await info.process.stderr.read() if info.process.stderr else b""
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")[-500:]
            await self._notifier.session_error(
                project=info.project_name, error=stderr_text or f"exit code {returncode}"
            )
