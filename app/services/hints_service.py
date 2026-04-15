"""Service for managing persisted agent schedule hints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

from app.services.optimizer import DAYS

DEFAULT_HINTS_FILE = Path("data/agent_hints.json")


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def _ensure_data_directory() -> None:
    DEFAULT_HINTS_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_hints(path: Optional[Path] = None) -> Dict[str, Tuple[str, str, bool]]:
    """Load agent hints from JSON, returning empty dict if file is missing."""
    path = path or DEFAULT_HINTS_FILE
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        saved = json.load(f)
    return {
        wo_id: (entry["day"], entry["trade"], entry["scheduled"])
        for wo_id, entry in saved.items()
    }


def save_hints(
    hints: Dict[str, Tuple[str, str, bool]], path: Optional[Path] = None
) -> None:
    """Write agent hints to JSON file."""
    path = path or DEFAULT_HINTS_FILE
    _ensure_data_directory()
    payload = {
        wo_id: {"day": day, "trade": trade, "scheduled": scheduled}
        for wo_id, (day, trade, scheduled) in hints.items()
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_hint(day: str, trade: str, scheduled: bool) -> None:
    """Raise ValueError if a single hint entry is invalid."""
    if day not in DAYS:
        raise ValueError(f"Invalid day {day!r}; must be one of {DAYS}")
    if not isinstance(trade, str) or not trade.strip():
        raise ValueError("trade must be a non-empty string")
    if not isinstance(scheduled, bool):
        raise ValueError(f"scheduled must be a bool, got {type(scheduled).__name__}")
