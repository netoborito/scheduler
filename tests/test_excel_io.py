"""Tests for Excel schedule export."""

from datetime import date

from app.models.domain import Assignment, Schedule, WorkOrder
from app.services.excel_io import build_schedule_workbook


def test_build_schedule_workbook_headers_and_rows():
    start = date(2026, 4, 6)
    wos = [
        WorkOrder(
            id=1,
            description="First job",
            duration_hours=8.0,
            priority=1,
            schedule_date=start,
            trade="NC-E/I",
            equipment="EQ-A",
        ),
        WorkOrder(
            id=2,
            description="Second job",
            duration_hours=4.0,
            priority=2,
            schedule_date=start,
            trade="NC-E/I",
            equipment="EQ-B",
        ),
    ]
    schedule = Schedule(
        assignments=[
            Assignment(work_order_id="1", day_offset=0, resource_id="NC-E/I"),
            Assignment(work_order_id="2", day_offset=1, resource_id="NC-E/I"),
        ],
        horizon_days=7,
        start_date=start,
    )

    wb = build_schedule_workbook(schedule, work_orders=wos)
    ws = wb.active

    assert ws.title == "Schedule"
    rows = list(ws.iter_rows(min_row=1, max_row=3, values_only=True))
    assert rows[0][0] == "work_order_id"
    assert rows[0][-1] == "schedule_line"

    # Header + 2 data rows
    assert ws.max_row == 3

    assert rows[1][0] == "1"
    assert rows[1][1] == "NC-E/I"
    assert rows[1][2] == "First job"
    assert float(rows[1][7]) == 8.0  # duration_hours

    assert rows[2][11] == date(2026, 4, 7).isoformat()  # schedule_date: start + 1 day
