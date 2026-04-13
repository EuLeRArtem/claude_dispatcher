import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULTS = {"sessions": True, "limits": True, "permissions": True}


class NotificationSettings:
    def __init__(self, path: str = "data/notifications.json"):
        self._path = Path(path)
        self._state: dict[str, bool] = self._load()

    def _load(self) -> dict[str, bool]:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {k: data.get(k, True) for k in _DEFAULTS}
            except Exception:
                logger.warning("Failed to load %s, using defaults", self._path)
        return dict(_DEFAULTS)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._state, f)

    def is_enabled(self, category: str) -> bool:
        return self._state.get(category, True)

    def toggle(self, category: str) -> bool:
        self._state[category] = not self._state.get(category, True)
        self._save()
        return self._state[category]

    def all_states(self) -> dict[str, bool]:
        return dict(self._state)
