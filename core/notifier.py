import logging

from telegram import Bot

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot: Bot, chat_id: int):
        self._bot = bot
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        try:
            await self._bot.send_message(
                chat_id=self._chat_id, text=text, parse_mode="HTML"
            )
        except Exception:
            logger.exception("Failed to send notification")

    async def session_started(
        self, project: str, mode: str, url: str | None = None
    ) -> None:
        if mode == "remote" and url:
            text = f"🚀 <b>{project}</b>: сессия запущена\n📎 {url}"
        elif mode == "remote":
            text = f"🚀 <b>{project}</b>: remote-control запущен\n💻 URL в окне терминала"
        else:
            text = f"🚀 <b>{project}</b>: задача запущена"
        await self.send(text)

    async def session_finished(self, project: str, duration_min: int) -> None:
        await self.send(
            f"✅ <b>{project}</b>: завершилась ({duration_min} мин)"
        )

    async def session_error(self, project: str, error: str) -> None:
        await self.send(f"❌ <b>{project}</b>: ошибка\n<pre>{error}</pre>")

    async def rate_limit(self, project: str) -> None:
        await self.send(f"⏸️ <b>{project}</b>: rate limit, ожидание")

    async def limit_warning(
        self, period: str, percent: int, reset_minutes: int
    ) -> None:
        icons = {70: "⚠️", 85: "⛔", 95: "🔴"}
        icon = icons.get(percent, "⚠️")
        await self.send(
            f"{icon} {period} лимит {percent}% — reset через {reset_minutes} мин"
        )

    async def permission_needed(
        self, project: str, url: str | None, message: str
    ) -> None:
        link = f"\n📎 {url}" if url else ""
        await self.send(f"⚠️ <b>{project}</b>: ждёт разрешения\n{message}{link}")

    async def agent_idle(self, project: str, url: str | None = None) -> None:
        link = f"\n📎 {url}" if url else ""
        await self.send(f"💤 <b>{project}</b>: агент завершил, ждёт ввода{link}")

    async def agent_stopped(
        self, project: str, error: str, details: str = ""
    ) -> None:
        detail_text = f"\n<pre>{details[:300]}</pre>" if details else ""
        await self.send(f"⛔ <b>{project}</b>: {error}{detail_text}")
