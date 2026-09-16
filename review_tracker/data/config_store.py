"""Local application settings, stored as JSON in the user's home directory."""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".gitlab_review_tracker.json"
MAX_PROJECT_HISTORY = 15


def add_to_history(history: list[str], value: str) -> list[str]:
    value = value.strip()
    if not value:
        return history
    history = [v for v in history if v != value]
    history.insert(0, value)
    return history[:MAX_PROJECT_HISTORY]


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
