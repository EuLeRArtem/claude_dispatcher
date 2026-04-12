import json
import pytest
from pathlib import Path

from core.transcript_parser import parse_transcript, SessionUsage


@pytest.fixture
def transcript_file(tmp_path):
    """Create a minimal JSONL transcript with 3 assistant messages."""
    lines = [
        {"type": "system", "subtype": "bridge_status", "content": "ready", "timestamp": "2026-04-12T10:00:00Z"},
        {"type": "human", "content": [{"type": "text", "text": "hello"}], "timestamp": "2026-04-12T10:01:00Z"},
        {
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-6",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 500,
                    "cache_read_input_tokens": 5000,
                    "cache_creation_input_tokens": 200,
                },
            },
            "timestamp": "2026-04-12T10:01:05Z",
        },
        {"type": "human", "content": [{"type": "text", "text": "fix bug"}], "timestamp": "2026-04-12T10:02:00Z"},
        {
            "type": "assistant",
            "message": {
                "model": "claude-opus-4-6",
                "usage": {
                    "input_tokens": 150,
                    "output_tokens": 800,
                    "cache_read_input_tokens": 6000,
                    "cache_creation_input_tokens": 0,
                },
            },
            "timestamp": "2026-04-12T10:02:10Z",
        },
        {
            "type": "assistant",
            "message": {
                "model": "claude-haiku-4-5-20251001",
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 100,
                    "cache_read_input_tokens": 1000,
                    "cache_creation_input_tokens": 0,
                },
            },
            "timestamp": "2026-04-12T10:03:00Z",
        },
    ]
    p = tmp_path / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(l) for l in lines), encoding="utf-8")
    return str(p)


def test_parse_transcript_sums_usage(transcript_file):
    result = parse_transcript(transcript_file)
    assert result is not None
    assert result.input_tokens == 300        # 100 + 150 + 50
    assert result.output_tokens == 1400      # 500 + 800 + 100
    assert result.cache_read_input_tokens == 12000  # 5000 + 6000 + 1000
    assert result.cache_creation_input_tokens == 200
    assert result.request_count == 3


def test_parse_transcript_picks_most_common_model(transcript_file):
    result = parse_transcript(transcript_file)
    assert result is not None
    assert result.model == "claude-opus-4-6"  # 2 opus vs 1 haiku


def test_parse_transcript_missing_file():
    result = parse_transcript("/nonexistent/path.jsonl")
    assert result is None


def test_parse_transcript_no_assistant_messages(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text(json.dumps({"type": "system", "content": "init"}), encoding="utf-8")
    result = parse_transcript(str(p))
    assert result is None


def test_parse_transcript_missing_usage_fields(tmp_path):
    """Assistant message with partial usage — missing fields default to 0."""
    line = {
        "type": "assistant",
        "message": {
            "model": "claude-opus-4-6",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        },
    }
    p = tmp_path / "partial.jsonl"
    p.write_text(json.dumps(line), encoding="utf-8")
    result = parse_transcript(str(p))
    assert result is not None
    assert result.cache_read_input_tokens == 0
    assert result.cache_creation_input_tokens == 0
