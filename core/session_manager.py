import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.notifier import Notifier

logger = logging.getLogger(__name__)

_REMOTE_URL_RE = re.compile(r"(https://claude\.ai/code/session_\S+)")
_IS_WINDOWS = sys.platform == "win32"

# IDE CLI command mapping
_IDE_CLI = {
    "vscode": "code",
    "cursor": "cursor",
}

TRIGGER_DIR = Path.home() / ".claude-dispatcher"
TRIGGER_FILE = TRIGGER_DIR / "terminal.json"
ACK_FILE = TRIGGER_DIR / "terminal.ack"
READY_FILE = TRIGGER_DIR / "ide-ready.ack"


def _find_claude() -> str:
    """Find claude executable. On Windows, prefer .cmd wrapper."""
    if _IS_WINDOWS:
        cmd_path = shutil.which("claude.cmd") or shutil.which("claude")
        if cmd_path:
            return cmd_path
    return shutil.which("claude") or "claude"


def _get_env() -> dict[str, str]:
    """Get environment with Windows-specific overrides for claude CLI."""
    env = os.environ.copy()
    # Remove bot's venv vars so Claude doesn't inherit them
    for key in ("VIRTUAL_ENV", "_OLD_VIRTUAL_PATH", "_OLD_VIRTUAL_PROMPT"):
        env.pop(key, None)
    if _IS_WINDOWS and "CLAUDE_CODE_GIT_BASH_PATH" not in env:
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
    process: object  # asyncio.subprocess.Process or subprocess.Popen or None
    url: str | None = None
    _url_file: str | None = None
    _killed: bool = False

    def duration_minutes(self) -> int:
        delta = datetime.now(timezone.utc) - self.started_at
        return int(delta.total_seconds() / 60)


class SessionManager:
    def __init__(self, notifier: Notifier, ide: str = "none"):
        self._notifier = notifier
        self._ide = ide
        self._sessions: dict[str, SessionInfo] = {}

    def list_sessions(self) -> list[SessionInfo]:
        return list(self._sessions.values())

    def get_session(self, session_id: str) -> SessionInfo | None:
        return self._sessions.get(session_id)

    # --- Public API ---

    async def start_remote(self, project_name: str, project_path: str, prompt: str = "") -> SessionInfo:
        claude = _find_claude()
        session_id = str(uuid.uuid4())[:8]

        if _IS_WINDOWS:
            return await self._start_remote_windows(
                session_id, claude, project_name, project_path, prompt
            )

        # Unix: pipe stdout to capture URL
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
        asyncio.create_task(self._monitor_process(info))
        return info

    async def kill_session(self, session_id: str) -> bool:
        info = self._sessions.get(session_id)
        if not info:
            return False

        info._killed = True
        proc = info.process

        if proc is None:
            # IDE-managed session — send kill trigger to extension
            kill_trigger = {
                "title": f"Claude: {info.project_name}",
                "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            }
            TRIGGER_DIR.mkdir(parents=True, exist_ok=True)
            kill_file = TRIGGER_DIR / "terminal-kill.json"
            kill_file.write_text(json.dumps(kill_trigger), encoding="utf-8")
            self._sessions.pop(session_id, None)
            return True

        if isinstance(proc, subprocess.Popen):
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

        if info._url_file:
            try:
                os.unlink(info._url_file)
            except OSError:
                pass

        self._sessions.pop(session_id, None)
        return True

    # --- Windows remote-control ---

    async def _start_remote_windows(
        self, session_id: str, claude: str,
        project_name: str, project_path: str, prompt: str,
    ) -> SessionInfo:
        """Start remote-control on Windows — via IDE terminal or plain console."""
        if self._ide in _IDE_CLI:
            return await self._start_remote_ide(
                session_id, claude, project_name, project_path, prompt
            )
        return await self._start_remote_console(
            session_id, claude, project_name, project_path, prompt
        )

    async def _ensure_ide_ready(self, project_path: str) -> bool:
        """Ensure IDE is open with the project and extension is active.

        1. Check if extension heartbeat is fresh (< 15s)
        2. If not — launch IDE with project path and wait for heartbeat
        """
        ide_cmd = shutil.which(_IDE_CLI[self._ide])
        if not ide_cmd:
            logger.warning("IDE CLI '%s' not found in PATH", _IDE_CLI[self._ide])
            return False

        if self._is_extension_ready():
            logger.info("IDE extension already active")
            subprocess.Popen([ide_cmd, project_path], creationflags=subprocess.CREATE_NO_WINDOW)
            await asyncio.sleep(1)
            return True

        # Launch IDE with the project
        logger.info("Launching %s for %s", ide_cmd, project_path)
        subprocess.Popen([ide_cmd, project_path], creationflags=subprocess.CREATE_NO_WINDOW)

        # Wait for extension to become ready (heartbeat file)
        for _ in range(30):  # 15 seconds
            await asyncio.sleep(0.5)
            if self._is_extension_ready():
                logger.info("IDE extension became ready")
                return True

        logger.warning("IDE extension did not become ready in 15s")
        return False

    @staticmethod
    def _is_extension_ready() -> bool:
        """Check if the IDE extension heartbeat is fresh (< 15 seconds)."""
        try:
            if not READY_FILE.exists():
                return False
            ts = int(READY_FILE.read_text().strip())
            age_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - ts
            return age_ms < 15_000
        except (ValueError, OSError):
            return False

    async def _start_remote_ide(
        self, session_id: str, claude: str,
        project_name: str, project_path: str, prompt: str,
    ) -> SessionInfo:
        """Start remote-control via IDE integrated terminal.

        Flow: ensure IDE ready → write trigger → wait for ack → done.
        Falls back to console if IDE is unavailable.
        """
        ide_ready = await self._ensure_ide_ready(project_path)
        if not ide_ready:
            logger.warning("Falling back to console mode")
            return await self._start_remote_console(
                session_id, claude, project_name, project_path, prompt
            )

        # Build command string for the terminal
        cmd_str = claude + " --remote-control"
        if prompt:
            cmd_str += f' "{prompt}"'

        # Write trigger file
        TRIGGER_DIR.mkdir(parents=True, exist_ok=True)
        trigger = {
            "cwd": project_path,
            "command": cmd_str,
            "title": f"Claude: {project_name}",
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        }
        TRIGGER_FILE.write_text(json.dumps(trigger), encoding="utf-8")

        logger.info("Remote control (IDE): trigger=%s", trigger)

        # Wait for extension to pick it up
        picked_up = False
        for _ in range(10):  # 5 seconds
            await asyncio.sleep(0.5)
            if ACK_FILE.exists():
                try:
                    ack_ts = ACK_FILE.read_text().strip()
                    if ack_ts == str(trigger["timestamp"]):
                        picked_up = True
                        break
                except OSError:
                    pass

        if not picked_up:
            logger.warning("IDE extension did not pick up trigger, falling back to console")
            return await self._start_remote_console(
                session_id, claude, project_name, project_path, prompt
            )

        # IDE owns the process
        info = SessionInfo(
            session_id=session_id,
            project_name=project_name,
            mode="remote",
            started_at=datetime.now(timezone.utc),
            process=None,
        )
        self._sessions[session_id] = info

        await self._notifier.session_started(project=project_name, mode="remote")
        return info

    async def _start_remote_console(
        self, session_id: str, claude: str,
        project_name: str, project_path: str, prompt: str,
    ) -> SessionInfo:
        """Start remote-control in a visible console window (fallback)."""
        env = _get_env()
        cmd = [claude, "--remote-control"]
        if prompt:
            cmd.append(prompt)

        logger.info("Remote control (console): cmd=%s cwd=%s", cmd, project_path)

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

        await self._notifier.session_started(project=project_name, mode="remote")
        asyncio.create_task(self._monitor_popen(info))
        return info

    # --- Output readers & monitors ---

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
            while True:
                chunk = await info.process.stdout.read(4096)
                if not chunk:
                    break
        except Exception:
            logger.exception("Error reading remote output for %s", info.project_name)

    async def _monitor_popen(self, info: SessionInfo) -> None:
        """Monitor a subprocess.Popen process (Windows console mode)."""
        proc = info.process
        while proc.poll() is None:
            await asyncio.sleep(2)

        duration = info.duration_minutes()
        self._sessions.pop(info.session_id, None)

        if info._killed:
            return

        if proc.returncode == 0:
            await self._notifier.session_finished(
                project=info.project_name, duration_min=duration
            )
        else:
            await self._notifier.session_error(
                project=info.project_name, error=f"exit code {proc.returncode}"
            )

    async def _monitor_process(self, info: SessionInfo) -> None:
        returncode = await info.process.wait()
        duration = info.duration_minutes()
        self._sessions.pop(info.session_id, None)

        if info._killed:
            return

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
