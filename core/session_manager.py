import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

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


def _get_env() -> dict[str, str]:
    """Get environment with Windows-specific overrides for claude CLI."""
    import os
    env = os.environ.copy()
    if _IS_WINDOWS and "CLAUDE_CODE_GIT_BASH_PATH" not in env:
        # claude -p on Windows requires git-bash
        git_bash = shutil.which("bash", path=r"C:\Program Files\Git\bin") or \
                   shutil.which("bash", path=r"C:\Users\patri\AppData\Local\Programs\Git\bin")
        if git_bash:
            env["CLAUDE_CODE_GIT_BASH_PATH"] = git_bash
    return env


async def _create_process(cmd: list[str], cwd: str) -> asyncio.subprocess.Process:
    """Create subprocess, handling Windows .cmd files."""
    env = _get_env()
    logger.info("Starting process: cmd=%s cwd=%s", cmd, cwd)
    if _IS_WINDOWS:
        shell_cmd = subprocess.list2cmdline(cmd)
        logger.info("Shell command: %s", shell_cmd)
        return await asyncio.create_subprocess_shell(
            shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
    return await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
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
    process: object  # asyncio.subprocess.Process or subprocess.Popen
    url: str | None = None
    _url_file: str | None = None

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
        session_id = str(uuid.uuid4())[:8]

        if _IS_WINDOWS:
            return await self._start_remote_windows(
                session_id, claude, project_name, project_path, prompt
            )

        # Unix: pipe stdout to capture URL (no visible terminal needed)
        cmd = [claude, "--remote-control"]
        if prompt:
            cmd.append(prompt)
        process = await _create_process(cmd, cwd=project_path)
        info = SessionInfo(
            session_id=session_id,
            project_name=project_name,
            mode="remote",
            started_at=datetime.now(timezone.utc),
            process=process,
        )
        self._sessions[session_id] = info
        asyncio.create_task(self._read_remote_output(info))
        asyncio.create_task(self._monitor_process(info))
        return info

    async def _start_remote_windows(
        self, session_id: str, claude: str,
        project_name: str, project_path: str, prompt: str,
    ) -> SessionInfo:
        """Start remote-control in a visible console window on Windows.
        Claude writes directly to console (not stdout), so we can't pipe the URL.
        Instead, we open a visible terminal and notify the user.
        """
        env = _get_env()

        cmd = [claude, "--remote-control"]
        if prompt:
            cmd.append(prompt)

        logger.info("Remote control (visible console): cmd=%s cwd=%s", cmd, project_path)

        process = subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            cwd=project_path,
            env=env,
        )

        info = SessionInfo(
            session_id=session_id,
            project_name=project_name,
            mode="remote",
            started_at=datetime.now(timezone.utc),
            process=process,
        )
        self._sessions[session_id] = info

        # Notify — URL is visible in the terminal window
        await self._notifier.session_started(project=project_name, mode="remote")
        # Monitor process lifecycle
        asyncio.create_task(self._monitor_popen(info))

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

        proc = info.process
        if isinstance(proc, subprocess.Popen):
            # On Windows, terminate() only kills the parent — use taskkill /T to kill the tree
            if _IS_WINDOWS:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True, timeout=10,
                    )
                except Exception:
                    proc.kill()
            else:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        else:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

        # Cleanup temp file
        if info._url_file:
            try:
                os.unlink(info._url_file)
            except OSError:
                pass

        self._sessions.pop(session_id, None)
        return True

    # --- Remote control (Unix): pipe stdout to capture URL ---

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

    # --- Remote control (Windows): visible console + poll temp file ---

    async def _poll_url_file(self, info: SessionInfo) -> None:
        """Poll the temp file written by Tee-Object for the session URL."""
        url_file = Path(info._url_file)
        try:
            for _ in range(60):  # Try for 60 seconds
                await asyncio.sleep(1)
                if not url_file.exists():
                    continue
                try:
                    content = url_file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                url = parse_remote_url(content)
                if url:
                    info.url = url
                    await self._notifier.session_started(
                        project=info.project_name, mode="remote", url=url
                    )
                    return
            # Timeout — notify without URL
            await self._notifier.session_started(
                project=info.project_name, mode="remote"
            )
        except Exception:
            logger.exception("Error polling URL file for %s", info.project_name)

    async def _monitor_popen(self, info: SessionInfo) -> None:
        """Monitor a subprocess.Popen process (used for Windows remote-control)."""
        proc = info.process
        while proc.poll() is None:
            await asyncio.sleep(2)

        returncode = proc.returncode
        duration = info.duration_minutes()
        self._sessions.pop(info.session_id, None)

        # Cleanup temp file
        if info._url_file:
            try:
                os.unlink(info._url_file)
            except OSError:
                pass

        if returncode == 0:
            await self._notifier.session_finished(
                project=info.project_name, duration_min=duration
            )
        else:
            await self._notifier.session_error(
                project=info.project_name, error=f"exit code {returncode}"
            )

    # --- Normal mode: pipe stdout, no visible window ---

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
