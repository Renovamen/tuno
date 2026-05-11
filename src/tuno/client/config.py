"""Local client configuration persistence."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

MAX_SERVER_HISTORY = 20


def default_config_path() -> Path:
    """Return the client YAML config path for the current platform environment."""
    override = os.environ.get("TUNO_CONFIG_FILE")
    if override:
        return Path(override).expanduser()

    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "tuno" / "config.yaml"


def load_server_history(path: Path | None = None) -> list[str]:
    """Load saved server URLs from the client YAML config."""
    raw_history = _load_config(path).get("server_history", [])
    if not isinstance(raw_history, list):
        return []

    history: list[str] = []
    for item in raw_history:
        if isinstance(item, str):
            value = item.strip()
            if value and value not in history:
                history.append(value)

    return history


def remember_server(url: str, path: Path | None = None) -> list[str]:
    """Persist one server URL as the most recent history entry."""
    normalized = url.strip()
    if not normalized:
        return load_server_history(path)

    history = [item for item in load_server_history(path) if item != normalized]
    history.insert(0, normalized)
    history = history[:MAX_SERVER_HISTORY]
    save_server_history(history, path)
    return history


def save_server_history(history: list[str], path: Path | None = None) -> None:
    """Write server history to the client YAML config."""
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    unique_history: list[str] = []
    for item in history:
        value = item.strip()
        if value and value not in unique_history:
            unique_history.append(value)

    config = _load_config(config_path)
    config["server_history"] = unique_history[:MAX_SERVER_HISTORY]
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or default_config_path()
    try:
        with config_path.open(encoding="utf-8") as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        return {}
    except (OSError, yaml.YAMLError):
        return {}

    return config if isinstance(config, dict) else {}
