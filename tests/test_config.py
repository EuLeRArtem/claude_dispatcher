import json
import os
import pytest
from unittest.mock import patch


def test_load_config_from_file(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "projects_dir": "D:\\projects",
        "poll_interval_sec": 30,
        "thresholds": [60, 80, 90],
        "log_level": "DEBUG"
    }))

    env = {
        "TELEGRAM_BOT_TOKEN": "test-token-123",
        "TELEGRAM_USER_ID": "999",
    }

    with patch.dict(os.environ, env, clear=False):
        from config import load_config
        cfg = load_config(config_path=str(config_path))

    assert cfg.telegram_bot_token == "test-token-123"
    assert cfg.telegram_user_id == 999
    assert cfg.projects_dir == "D:\\projects"
    assert cfg.poll_interval_sec == 30
    assert cfg.thresholds == [60, 80, 90]
    assert cfg.log_level == "DEBUG"


def test_load_config_defaults(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")

    env = {
        "TELEGRAM_BOT_TOKEN": "tok",
        "TELEGRAM_USER_ID": "1",
    }

    with patch.dict(os.environ, env, clear=False):
        from config import load_config
        cfg = load_config(config_path=str(config_path))

    assert cfg.poll_interval_sec == 60
    assert cfg.thresholds == [70, 85, 95]
    assert cfg.log_level == "INFO"


def test_load_config_missing_token(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}")

    env = {"TELEGRAM_USER_ID": "1"}
    with patch.dict(os.environ, env, clear=False), \
         patch("config.load_dotenv"):  # Don't load .env file
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        from config import load_config
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            load_config(config_path=str(config_path))


def test_claude_credentials_path():
    from config import get_claude_credentials_path
    path = get_claude_credentials_path()
    assert ".claude" in path
    assert path.endswith(".credentials.json")
