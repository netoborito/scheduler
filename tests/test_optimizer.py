"""Tests for schedule optimizer."""

from datetime import date
from unittest.mock import patch

from app.models.domain import WorkOrder
from app.models.shift import Shift
from app.services.optimizer import optimize_schedule


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
