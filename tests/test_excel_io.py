"""Tests for Excel schedule export and backlog fetch."""

from datetime import date
from unittest.mock import MagicMock

import pandas as pd

from app.models.domain import Assignment, Schedule, WorkOrder
from app.services.excel_io import build_schedule_workbook, fetch_backlog


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


def test_fetch_backlog_converts_api_dataframe(monkeypatch):
    start = date(2026, 4, 6)
    df = pd.DataFrame(
        [
            {
                "Work Order": "5001",
                "Description": "Fix motor",
                "Estimated Hours": "4",
                "Trade": "ELEC",
                "Type": "Corrective",
                "Status": "Open - Ready to Schedule",
                "Sched. Start Date": "2026-04-07",
                "Priority": "1-Critical",
                "Safety": "",
                "Class": "",
                "Date Created": "2026-03-01",
                "Department": "MFG",
                "Equipment": "EQ-100",
                "People Required": "2",
            },
            {
                "Work Order": "5002",
                "Description": "No trade row",
                "Estimated Hours": "1",
                "Trade": "",
                "Type": "Corrective",
                "Status": "Open - Ready to Schedule",
                "Sched. Start Date": "2026-04-07",
                "Priority": "2-Urgent",
                "Safety": "",
                "Class": "",
                "Date Created": "2026-03-01",
                "Department": "MFG",
                "Equipment": "EQ-200",
                "People Required": "1",
            },
        ]
    )

    mock_client = MagicMock()
    mock_client.fetch_backlog.return_value = df
    monkeypatch.setattr(
        "app.services.excel_io.CloudBacklogClient",
        lambda: mock_client,
    )

    result = fetch_backlog(start_date=start, horizon_days=30)

    assert len(result) == 1
    wo = result[0]
    assert wo.id == "5001"
    assert wo.trade == "ELEC"
    assert wo.duration_hours == 4.0
    assert wo.priority == 3  # "1-Critical" -> 1 + 2
    assert wo.description == "Fix motor"
    assert wo.equipment == "EQ-100"
    assert wo.num_people == 2
    assert wo.dept == "MFG"
