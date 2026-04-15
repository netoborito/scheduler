"""Service for managing optimizer objective gains stored in JSON format."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from app.services.optimizer import DEFAULT_OBJECTIVE_GAINS

DEFAULT_GAINS_FILE = Path("data/gains.json")


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def _ensure_data_directory() -> None:
    DEFAULT_GAINS_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_gains(path: Optional[Path] = None) -> Dict[str, float]:
    """Load gains from JSON file, falling back to DEFAULT_OBJECTIVE_GAINS."""
    path = path or DEFAULT_GAINS_FILE
    if not path.exists():
        return dict(DEFAULT_OBJECTIVE_GAINS)
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        return {**DEFAULT_OBJECTIVE_GAINS, **saved}
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"Invalid gains data in {path}: {e}") from e


def save_gains(gains: Dict[str, float], path: Optional[Path] = None) -> None:
    """Write gains to JSON file."""
    path = path or DEFAULT_GAINS_FILE
    _ensure_data_directory()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(gains, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_gains(gains: Dict[str, float]) -> None:
    """Raise ValueError if gains contain unknown keys, bad values, or unsafe ratios."""
    for key in gains:
        if key not in DEFAULT_OBJECTIVE_GAINS:
            raise ValueError(f"Unknown gain key: {key!r}")
    for key, value in gains.items():
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"Gain {key!r} must be a non-negative number, got {value!r}")
    merged = {**DEFAULT_OBJECTIVE_GAINS, **gains}
    if merged["schedule_bonus"] <= merged["load_balance"]:
        raise ValueError(
            f"schedule_bonus ({merged['schedule_bonus']}) must be greater than "
            f"load_balance ({merged['load_balance']}) to ensure work orders get assigned"
        )
