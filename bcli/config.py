"""Optional config file: ~/.config/bcli/config.json

Environment variables win over the file; both win over built-in defaults.
Keys used today: asr_python, asr_model, asr_worker.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("BCLI_CONFIG_DIR", Path.home() / ".config" / "bcli"))
CONFIG_FILE = CONFIG_DIR / "config.json"


def _file() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(CONFIG_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get(key: str, default: Any = None) -> Any:
    env = os.environ.get(f"BCLI_{key.upper()}")
    if env:
        return env
    value = _file().get(key)
    return value if value not in (None, "") else default
