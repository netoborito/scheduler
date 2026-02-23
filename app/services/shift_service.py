"""Service for managing shift data stored in JSON format."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from app.models.shift import Shift

# Default location for shifts JSON file
DEFAULT_SHIFTS_FILE = Path("data/shifts.json")


def ensure_data_directory() -> Path:
    """Ensure the data directory exists."""
    data_dir = DEFAULT_SHIFTS_FILE.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def load_shifts(shifts_file: Optional[Path] = None) -> List[Shift]:
    """Load shifts from JSON file.

    Args:
        shifts_file: Path to JSON file. If None, uses default location.

    Returns:
        List of Shift objects.
    """
    if shifts_file is None:
        shifts_file = DEFAULT_SHIFTS_FILE

    if not shifts_file.exists():
        return []

    try:
        with open(shifts_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            shifts_sorted = [Shift.from_dict(shift_data) for shift_data in data]
            return sorted(shifts_sorted, key=lambda x: x.trade)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ValueError(f"Invalid shift data in {shifts_file}: {e}") from e


def save_shifts(shifts: List[Shift], shifts_file: Optional[Path] = None) -> None:
    """Save shifts to JSON file.

    Args:
        shifts: List of Shift objects to save.
        shifts_file: Path to JSON file. If None, uses default location.
    """
    if shifts_file is None:
        shifts_file = DEFAULT_SHIFTS_FILE

    ensure_data_directory()

    data = [shift.to_dict() for shift in shifts]

    with open(shifts_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_shift_by_trade(
    trade: str, shifts_file: Optional[Path] = None
) -> Optional[Shift]:
    """Get a shift by trade name.

    Args:
        trade: Trade name to search for.
        shifts_file: Path to JSON file. If None, uses default location.

    Returns:
        Shift object if found, None otherwise.
    """
    shifts = load_shifts(shifts_file)
    for shift in shifts:
        if shift.trade == trade:
            return shift
    return None


def add_shift(shift: Shift, shifts_file: Optional[Path] = None) -> None:
    """Add a new shift to the JSON file.

    Args:
        shift: Shift object to add.
        shifts_file: Path to JSON file. If None, uses default location.

    Raises:
        ValueError: If a shift with the same trade already exists.
    """
    shifts = load_shifts(shifts_file)
    # Check if shift with same trade already exists
    if any(s.trade == shift.trade for s in shifts):
        raise ValueError(f"Shift with trade '{shift.trade}' already exists")
    shifts.append(shift)
    save_shifts(shifts, shifts_file)


def update_shift(
    trade: str, updated_shift: Shift, shifts_file: Optional[Path] = None
) -> None:
    """Update an existing shift by trade name.

    Args:
        trade: Trade name of the shift to update.
        updated_shift: Updated Shift object.
        shifts_file: Path to JSON file. If None, uses default location.

    Raises:
        ValueError: If shift with the given trade is not found.
    """
    shifts = load_shifts(shifts_file)
    found = False
    for i, shift in enumerate(shifts):
        if shift.trade == trade:
            shifts[i] = updated_shift
            found = True
            break
    if not found:
        raise ValueError(f"Shift with trade '{trade}' not found")
    save_shifts(shifts, shifts_file)


def delete_shift(trade: str, shifts_file: Optional[Path] = None) -> None:
    """Delete a shift by trade name.

    Args:
        trade: Trade name of the shift to delete.
        shifts_file: Path to JSON file. If None, uses default location.

    Raises:
        ValueError: If shift with the given trade is not found.
    """
    shifts = load_shifts(shifts_file)
    original_count = len(shifts)
    shifts = [s for s in shifts if s.trade != trade]
    if len(shifts) == original_count:
        raise ValueError(f"Shift with trade '{trade}' not found")
    save_shifts(shifts, shifts_file)


def get_all_shifts(shifts_file: Optional[Path] = None) -> List[Shift]:
    """Get all shifts.

    Args:
        shifts_file: Path to JSON file. If None, uses default location.

    Returns:
        List of all Shift objects.
    """
    return load_shifts(shifts_file)
