"""Tests for schedule optimizer."""

from datetime import date
from unittest.mock import patch

from app.models.domain import WorkOrder
from app.models.shift import Shift
from app.services.optimizer import (
    ScheduleOptimizer,
    apply_bzus_preferences,
    optimize_schedule,
)


def _sample_shifts():
    weekdays = dict(
        monday=True,
        tuesday=True,
        wednesday=True,
        thursday=True,
        friday=True,
        saturday=False,
        sunday=False,
    )
    return [
        Shift(
            trade="NC-E/I",
            shift_duration_hours=8,
            technicians_per_crew=6,
            **weekdays,
        ),
        Shift(
            trade="Mechanical",
            shift_duration_hours=8,
            technicians_per_crew=6,
            **weekdays,
        ),
    ]


@patch("app.services.optimizer.load_shifts")
def test_optimize_schedule_assigns_each_work_order(mock_load_shifts):
    mock_load_shifts.return_value = _sample_shifts()
    start_date = date(2026, 4, 6)
    work_orders = [
        WorkOrder(
            id=1,
            description="Test work order 1",
            duration_hours=8.0,
            priority=1,
            schedule_date=start_date,
            trade="NC-E/I",
        ),
        WorkOrder(
            id=2,
            description="Test work order 2",
            duration_hours=4.0,
            priority=2,
            schedule_date=start_date,
            trade="NC-E/I",
        ),
        WorkOrder(
            id=3,
            description="Test work order 3",
            duration_hours=6.0,
            priority=3,
            schedule_date=start_date,
            trade="Mechanical",
        ),
    ]

    schedule = optimize_schedule(work_orders=work_orders, start_date=start_date)

    assert schedule.start_date == start_date
    assert len(schedule.assignments) == 3
    assigned_ids = {str(a.work_order_id) for a in schedule.assignments}
    assert assigned_ids == {"1", "2", "3"}


# -- _is_hint tests ----------------------------------------------------------

_START = date(2026, 4, 6)
_WO = WorkOrder(
    id=1, description="WO 1", duration_hours=4.0,
    priority=1, schedule_date=_START, trade="NC-E/I",
)


def test_is_hint_positive():
    hints = {"1": ("monday", "NC-E/I", True)}
    opt = ScheduleOptimizer(work_orders=[_WO], start_date=_START, hints=hints)
    assert opt._is_hint("1", "NC-E/I", "monday") == 1


def test_is_hint_negative():
    hints = {"1": ("monday", "NC-E/I", True)}
    opt = ScheduleOptimizer(work_orders=[_WO], start_date=_START, hints=hints)
    # Wrong day
    assert opt._is_hint("1", "NC-E/I", "tuesday") == -1
    # Wrong trade
    assert opt._is_hint("1", "Mechanical", "monday") == -1
    # User explicitly unscheduled (False flag)
    hints_neg = {"1": ("monday", "NC-E/I", False)}
    opt_neg = ScheduleOptimizer(work_orders=[_WO], start_date=_START, hints=hints_neg)
    assert opt_neg._is_hint("1", "NC-E/I", "monday") == -1


def test_is_hint_no_hints():
    opt = ScheduleOptimizer(work_orders=[_WO], start_date=_START, hints={})
    assert opt._is_hint("1", "NC-E/I", "monday") == 0
    # Default (hints=None)
    opt_default = ScheduleOptimizer(work_orders=[_WO], start_date=_START)
    assert opt_default._is_hint("1", "NC-E/I", "monday") == 0


# -- Hints passthrough -------------------------------------------------------


def test_optimize_schedule_passes_hints():
    hints = {"1": ("monday", "NC-E/I", True), "2": ("tuesday", "NC-E/I", False)}
    opt = ScheduleOptimizer(work_orders=[_WO], start_date=_START, hints=hints)
    assert opt.hints == hints


def test_optimize_schedule_hints_default_empty():
    opt = ScheduleOptimizer(work_orders=[_WO], start_date=_START)
    assert opt.hints == {}


# -- apply_bzus_preferences ---------------------------------------------------


def _make_wo(trade: str, equipment: str = "") -> WorkOrder:
    return WorkOrder(
        id=1, description="WO", duration_hours=4.0,
        priority=1, schedule_date=_START, trade=trade, equipment=equipment,
    )


def test_bzus_ei_with_bz_400_remaps():
    result = apply_bzus_preferences([_make_wo("NC-E/I", "40012345")])
    assert result[0].trade == "NC-E/I PM"


def test_bzus_ei_with_bz_500_remaps():
    result = apply_bzus_preferences([_make_wo("NC-E/I", "50098765")])
    assert result[0].trade == "NC-E/I PM"


def test_bzus_ei_with_leading_zero_remaps():
    result = apply_bzus_preferences([_make_wo("NC-E/I", "040012345")])
    assert result[0].trade == "NC-E/I PM"


def test_bzus_ei_without_bz_unchanged():
    result = apply_bzus_preferences([_make_wo("NC-E/I", "60012345")])
    assert result[0].trade == "NC-E/I"


def test_bzus_ei_rejects_1400():
    result = apply_bzus_preferences([_make_wo("NC-E/I", "14001234")])
    assert result[0].trade == "NC-E/I"


def test_bzus_mechanic_bz_remaps_to_nights():
    result = apply_bzus_preferences([_make_wo("NC-MECHANIC", "40012345")])
    assert result[0].trade == "NC-PM NIGHTS"


def test_bzus_mechanic_non_bz_remaps_to_days():
    result = apply_bzus_preferences([_make_wo("NC-MECHANIC", "60012345")])
    assert result[0].trade == "NC-PM DAYS"


def test_bzus_mechanic_exe_untouched():
    result = apply_bzus_preferences([_make_wo("NC-MECHANIC EXE", "40012345")])
    assert result[0].trade == "NC-MECHANIC EXE"


def test_bzus_other_trade_untouched():
    result = apply_bzus_preferences([_make_wo("Electrical", "40012345")])
    assert result[0].trade == "Electrical"
