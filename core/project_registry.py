import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class ProjectRegistry:
    def __init__(self, data_file: str = "data/projects.json"):
        self._data_file = Path(data_file)
        self._projects: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self._data_file.exists():
            with open(self._data_file, "r", encoding="utf-8") as f:
                self._projects = json.load(f)

    def _save(self) -> None:
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._data_file, "w", encoding="utf-8") as f:
            json.dump(self._projects, f, ensure_ascii=False, indent=2)

    def scan(self, directory: str) -> list[dict]:
        results = []
        base = Path(directory)
        if not base.is_dir():
            return results
        for child in sorted(base.iterdir()):
            try:
                if child.is_dir() and (child / ".git").exists():
                    results.append({"name": child.name, "path": str(child)})
            except (OSError, PermissionError):
                continue
        return results

    def add(self, name: str, path: str) -> dict:
        if any(p["name"] == name for p in self._projects):
            raise ValueError(f"Project '{name}' already registered")
        project = {
            "name": name,
            "path": path,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self._projects.append(project)
        self._save()
        return project

    def remove(self, name: str) -> None:
        idx = next(
            (i for i, p in enumerate(self._projects) if p["name"] == name),
            None,
        )
        if idx is None:
            raise ValueError(f"Project '{name}' not found")
        self._projects.pop(idx)
        self._save()

    def list(self) -> list[dict]:
        return list(self._projects)

    def get(self, name: str) -> dict | None:
        return next(
            (p for p in self._projects if p["name"] == name), None
        )
