import json
import logging
from collections import Counter
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SessionUsage:
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    request_count: int


def parse_transcript(path: str) -> SessionUsage | None:
    """Parse a Claude Code JSONL transcript and sum token usage."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except (FileNotFoundError, OSError):
        logger.warning("Transcript not found: %s", path)
        return None

    models: list[str] = []
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }

    for line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "assistant" or "message" not in obj:
            continue
        msg = obj["message"]
        usage = msg.get("usage", {})
        model = msg.get("model", "unknown")
        models.append(model)
        for key in totals:
            totals[key] += usage.get(key, 0)

    if not models:
        return None

    most_common_model = Counter(models).most_common(1)[0][0]
    return SessionUsage(
        model=most_common_model,
        request_count=len(models),
        **totals,
    )
