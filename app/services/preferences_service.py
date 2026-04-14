"""Service for managing optimizer preference rules stored in JSON format."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_PREFERENCES_FILE = Path("data/preferences.json")


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def _ensure_data_directory() -> None:
    DEFAULT_PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_preferences(path: Optional[Path] = None) -> List[Dict]:
    """Load preference rules from JSON file (or [] if missing)."""
    path = path or DEFAULT_PREFERENCES_FILE
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, TypeError) as e:
        raise ValueError(f"Invalid preferences data in {path}: {e}") from e


def save_preferences(rules: List[Dict], path: Optional[Path] = None) -> None:
    """Write preference rules to JSON file."""
    path = path or DEFAULT_PREFERENCES_FILE
    _ensure_data_directory()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_rule(rule: Dict) -> None:
    """Raise ValueError if *rule* is malformed or contains invalid regex."""
    if "match" not in rule or "set" not in rule:
        raise ValueError("Rule must contain 'match' and 'set' keys")
    for field, pattern in rule["match"].items():
        try:
            re.compile(pattern)
        except re.error as e:
            raise ValueError(
                f"Invalid regex for field '{field}': {pattern!r} — {e}"
            ) from e
