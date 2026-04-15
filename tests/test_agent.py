"""Tests for agent API endpoints."""

from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.domain import WorkOrder
from app.models.shift import Shift

client = TestClient(app)


def _sample_shifts():
    weekdays = dict(
        monday=True, tuesday=True, wednesday=True,
        thursday=True, friday=True, saturday=False, sunday=False,
    )
    return [
        Shift(trade="NC-E/I", shift_duration_hours=8, technicians_per_crew=6, **weekdays),
        Shift(trade="Mechanical", shift_duration_hours=8, technicians_per_crew=6, **weekdays),
    ]


def _sample_work_orders(start: date):
    return [
        WorkOrder(id=1, description="WO-1", duration_hours=4, priority=1, schedule_date=start, trade="NC-E/I"),
        WorkOrder(id=2, description="WO-2", duration_hours=6, priority=2, schedule_date=start, trade="Mechanical"),
    ]


@patch("app.routes.agent.fetch_backlog")
@patch("app.services.optimizer.load_shifts")
@patch("app.routes.agent.get_next_monday")
def test_post_schedule_returns_flat_json(mock_monday, mock_shifts, mock_backlog):
    start = date(2026, 4, 6)
    mock_monday.return_value = start
    mock_shifts.return_value = _sample_shifts()
    mock_backlog.return_value = _sample_work_orders(start)

    resp = client.post("/api/agent/schedule")

    assert resp.status_code == 200
    data = resp.json()

    assert data["start_date"] == "2026-04-06"
    assert "gains" in data
    assert isinstance(data["assigned"], list)
    assert isinstance(data["unassigned"], list)
    assert len(data["assigned"]) == 2
    assert len(data["unassigned"]) == 0

    row = data["assigned"][0]
    assert "work_order_id" in row
    assert "date" in row
    assert "day_of_week" in row
    assert "trade" in row
    assert "manhours" in row

    summary = data["summary"]
    assert summary["total_work_orders"] == 2
    assert summary["assigned_count"] == 2
    assert summary["unassigned_count"] == 0
    assert "per_shift_daily_hours" in summary


# ---------------------------------------------------------------------------
# Hints endpoints
# ---------------------------------------------------------------------------


@patch("app.routes.agent.save_hints")
@patch("app.routes.agent.load_hints")
def test_put_and_get_hints(mock_load, mock_save):
    mock_load.return_value = {"42": ("monday", "NC-E/I", True)}

    resp = client.put("/api/agent/hints", json={
        "hints": [{"work_order_id": "42", "day": "monday", "trade": "NC-E/I", "scheduled": True}],
    })
    assert resp.status_code == 200
    assert resp.json()["count"] == 1

    resp = client.get("/api/agent/hints")
    assert resp.status_code == 200
    items = resp.json()["hints"]
    assert len(items) == 1
    assert items[0]["work_order_id"] == "42"


def test_put_hints_rejects_bad_day():
    resp = client.put("/api/agent/hints", json={
        "hints": [{"work_order_id": "1", "day": "funday", "trade": "NC-E/I", "scheduled": True}],
    })
    assert resp.status_code == 400
    assert "Invalid day" in resp.json()["detail"]


@patch("app.routes.agent.save_hints")
def test_delete_hints(mock_save):
    resp = client.delete("/api/agent/hints")
    assert resp.status_code == 200
    mock_save.assert_called_once_with({})


@patch("app.routes.agent.fetch_backlog")
@patch("app.services.optimizer.load_shifts")
@patch("app.routes.agent.get_next_monday")
@patch("app.routes.agent.load_hints")
def test_post_schedule_passes_hints(mock_hints, mock_monday, mock_shifts, mock_backlog):
    """Agent hints are forwarded to the optimizer."""
    start = date(2026, 4, 6)
    mock_monday.return_value = start
    mock_shifts.return_value = _sample_shifts()
    mock_backlog.return_value = _sample_work_orders(start)
    mock_hints.return_value = {"1": ("monday", "NC-E/I", True)}

    resp = client.post("/api/agent/schedule")
    assert resp.status_code == 200
    assert resp.json()["summary"]["assigned_count"] == 2
