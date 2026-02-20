"""Tests for shift service."""
import json
import tempfile
from pathlib import Path

from app.models.shift import Shift
from app.services.shift_service import (
    add_shift,
    delete_shift,
    get_all_shifts,
    get_shift_by_trade,
    load_shifts,
    save_shifts,
    update_shift,
)


def test_shift_model():
    """Test Shift model creation and serialization."""
    shift = Shift(
        trade="NC-E/I",
        shift_duration_hours=8,
        monday=True,
        tuesday=True,
        wednesday=True,
        thursday=True,
        friday=True,
        technicians_per_crew=2,
    )
    assert shift.trade == "NC-E/I"
    assert shift.shift_duration_hours == 8
    assert shift.monday is True
    assert shift.saturday is False
    assert shift.technicians_per_crew == 2

    # Test serialization
    shift_dict = shift.to_dict()
    assert shift_dict["trade"] == "NC-E/I"

    # Test deserialization
    shift2 = Shift.from_dict(shift_dict)
    assert shift2.trade == shift.trade


def test_save_and_load_shifts():
    """Test saving and loading shifts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        shifts_file = Path(tmpdir) / "shifts.json"
        shifts = [
            Shift(
                trade="NC-E/I",
                shift_duration_hours=8,
                monday=True,
                tuesday=True,
                technicians_per_crew=2,
            ),
            Shift(
                trade="Mechanical",
                shift_duration_hours=10,
                monday=True,
                friday=True,
                technicians_per_crew=1,
            ),
        ]

        save_shifts(shifts, shifts_file)
        assert shifts_file.exists()

        loaded_shifts = load_shifts(shifts_file)
        assert len(loaded_shifts) == 2
        assert loaded_shifts[0].trade == "NC-E/I"
        assert loaded_shifts[1].trade == "Mechanical"


def test_add_shift():
    """Test adding a new shift."""
    with tempfile.TemporaryDirectory() as tmpdir:
        shifts_file = Path(tmpdir) / "shifts.json"
        shift = Shift(
            trade="NewTrade",
            shift_duration_hours=8,
            monday=True,
            technicians_per_crew=1,
        )

        add_shift(shift, shifts_file)
        loaded = load_shifts(shifts_file)
        assert len(loaded) == 1
        assert loaded[0].trade == "NewTrade"


def test_get_shift_by_trade():
    """Test retrieving shift by trade."""
    with tempfile.TemporaryDirectory() as tmpdir:
        shifts_file = Path(tmpdir) / "shifts.json"
        shifts = [
            Shift(trade="Trade1", shift_duration_hours=8, monday=True),
            Shift(trade="Trade2", shift_duration_hours=10, tuesday=True),
        ]
        save_shifts(shifts, shifts_file)

        found = get_shift_by_trade("Trade1", shifts_file)
        assert found is not None
        assert found.trade == "Trade1"

        not_found = get_shift_by_trade("NonExistent", shifts_file)
        assert not_found is None


def test_update_shift():
    """Test updating an existing shift."""
    with tempfile.TemporaryDirectory() as tmpdir:
        shifts_file = Path(tmpdir) / "shifts.json"
        shift = Shift(
            trade="Trade1", shift_duration_hours=8, monday=True, technicians_per_crew=1
        )
        save_shifts([shift], shifts_file)

        updated = Shift(
            trade="Trade1",
            shift_duration_hours=10,
            monday=True,
            technicians_per_crew=2,
        )
        update_shift("Trade1", updated, shifts_file)

        loaded = load_shifts(shifts_file)
        assert loaded[0].shift_duration_hours == 10
        assert loaded[0].technicians_per_crew == 2


def test_delete_shift():
    """Test deleting a shift."""
    with tempfile.TemporaryDirectory() as tmpdir:
        shifts_file = Path(tmpdir) / "shifts.json"
        shifts = [
            Shift(trade="Trade1", shift_duration_hours=8, monday=True),
            Shift(trade="Trade2", shift_duration_hours=10, tuesday=True),
        ]
        save_shifts(shifts, shifts_file)

        delete_shift("Trade1", shifts_file)
        loaded = load_shifts(shifts_file)
        assert len(loaded) == 1
        assert loaded[0].trade == "Trade2"
