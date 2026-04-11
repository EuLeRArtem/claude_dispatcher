import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    telegram_bot_token: str
    telegram_user_id: int
    projects_dir: str = ""
    poll_interval_sec: int = 60
    thresholds: list[int] = field(default_factory=lambda: [70, 85, 95])
    log_level: str = "INFO"
    ide: str = "none"  # "vscode", "cursor", or "none" (plain console)


def load_config(config_path: str = "config.json") -> Config:
    load_dotenv()

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

    user_id_str = os.environ.get("TELEGRAM_USER_ID")
    if not user_id_str:
        raise ValueError("TELEGRAM_USER_ID is not set in .env")

    file_config = {}
    if Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            file_config = json.load(f)

    return Config(
        telegram_bot_token=bot_token,
        telegram_user_id=int(user_id_str),
        projects_dir=file_config.get("projects_dir", ""),
        poll_interval_sec=file_config.get("poll_interval_sec", 60),
        thresholds=file_config.get("thresholds", [70, 85, 95]),
        log_level=file_config.get("log_level", "INFO"),
        ide=file_config.get("ide", "none"),
    )


def get_claude_credentials_path() -> str:
    home = Path.home()
    return str(home / ".claude" / ".credentials.json")
