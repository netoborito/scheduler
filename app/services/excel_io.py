from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from typing import List, Optional
import json
import re
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

from app.models.domain import WorkOrder, Schedule
from app.utils.date_utils import get_next_monday


# Default scheduling horizon (days); used for filtering backlog to manageable size.
HORIZON_DAYS = 7


def _parse_priority(
    priority_str: str,
    wo_type: str = "",
    safety: bool = False,
) -> int:
    """Compute priority (1 = highest) from type, safety, and priority string.

    - Type "Preventive maintenance" -> 1
    - Safety (and not Preventive maintenance) -> 2
    - All others: first digit in priority_str + 2 (e.g. "1-Critical" -> 3,
      "2-Urgent" -> 4, "3-First Opportunity" -> 5; default 5 if no digit)
    """
    wo_type_normalized = (wo_type or "").strip()
    if wo_type_normalized == "Preventive maintenance":
        return 1
    if safety:
        return 2
    # First digit from priority_str + 2
    if pd.isna(priority_str):
        return 3 + 2  # 5
    s = str(priority_str).strip()
    if not s:
        return 5
    match = re.match(r"^(\d+)", s)
    if match:
        return int(match.group(1)) + 2
    return 5


def _parse_safety(safety_value, class_value) -> bool:
    safety_flag = False

    if pd.isna(class_value):
        class_value = ""
    if safety_value in ["yes", "true", "1", "y"] or class_value.lower() == "ehs":
        safety_flag = True
    return safety_flag


def _get_wo_age(value: pd.Timestamp | date) -> int:
    """Determine the age of a work order in days."""
    if pd.isna(value):
        return 0

    value_date = pd.to_datetime(value).date()
    return (date.today() - value_date).days


def load_and_filter(
    df: pd.DataFrame,
    start_date: date,
    horizon_days: int = HORIZON_DAYS,
) -> pd.DataFrame:
    """Filter the backlog DataFrame to work orders relevant to the scheduling horizon.

    - Drops column `Equipment Description` if present.
    - Keeps only rows with `Status == 'Open - Ready to Schedule'`.
    - Keeps only rows where `Sched Start Date` is missing (unscheduled) or falls
      within [start_date, start_date + horizon_days). Drops PMs due after scheduling horizon.
    """
    filtered = df.copy()
    filtered = filtered.drop(
        columns=["Equipment Description"], errors="ignore")

    if "Status" in filtered.columns:
        filtered = filtered[filtered["Status"] == "Open - Ready to Schedule"]

    filtered["Sched. Start Date"] = pd.to_datetime(
        filtered["Sched. Start Date"], errors="coerce"
    )

    end_date = start_date + timedelta(days=horizon_days)
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)

    # Remove PMs beyond the scheduling horizon
    beyond_horizon_PMs = (filtered.get("Type") == "Preventive maintenance") & (
        filtered["Sched. Start Date"] > pd.Timestamp(
            start_ts) + timedelta(days=horizon_days)
    )
    filtered = filtered[~beyond_horizon_PMs]

    # Keep: no date (NaT) or date in [start_date, end_date)
    current_wo_omitted = filtered["Sched. Start Date"].isna() | (
        (filtered["Sched. Start Date"] < start_ts)
        & (filtered["Sched. Start Date"] >= end_ts - timedelta(days=7))
    )

    filtered = filtered[~current_wo_omitted]

    return filtered


def parse_backlog_from_excel(
    xlsx_bytes: bytes,
    start_date: Optional[date] = None,
    horizon_days: Optional[int] = None,
) -> List[WorkOrder]:
    """Parse work order backlog from Excel and filter by scheduling horizon.

    Reads the Excel file, applies load_and_filter() to keep only work orders
    relevant to the horizon, then builds WorkOrder list from the filtered rows.

    Expects EAM export format with columns:
    - Work Order: Work order ID
    - Description: Work order description
    - Estimated Hs: Estimated hours (duration, converted to int - no fractional hours)
    - Priority: Priority text (e.g., "1-Critical", "2-Urgent/Scheduled")
    - Sched Start Date: Scheduled start date (used as due date)
    - Trade: Required trade/resource type for this work order
    - Type: Work order type (e.g. "Corrective")
    - Safety: Safety flag (Yes/No or boolean)
    """
    buffer = BytesIO(xlsx_bytes)
    df = pd.read_excel(buffer)

    if start_date is None:
        start_date = get_next_monday()
    if horizon_days is None:
        horizon_days = HORIZON_DAYS
    df = load_and_filter(df, start_date=start_date, horizon_days=horizon_days)

    work_orders: List[WorkOrder] = []
    for _, row in df.iterrows():

        # EAM Export format column mapping
        wo_id = str(row.get("Work Order", ""))
        description = str(row.get("Description", ""))

        # Convert duration to int (no fractional hours)
        duration_raw = row.get("Estimated Hs", 0.0)
        duration_hours = (
            1 if duration_raw <= 1 else int(
                round(float(duration_raw))) if not pd.isna(duration_raw) else 1
        )

        trade_raw = row.get("Trade", "")
        trade = str(trade_raw).strip() if not pd.isna(trade_raw) else ""

        type_raw = row.get("Type", "")
        wo_type = str(type_raw).strip() if not pd.isna(type_raw) else ""

        num_people_raw = row.get("Persons Required", 1)
        num_people = int(num_people_raw) if not pd.isna(num_people_raw) else 1

        equipment_raw = row.get("Equipment", "")
        equipment = str(equipment_raw).strip(
        ) if not pd.isna(equipment_raw) else ""

        dept_raw = row.get("Department", "")
        dept = str(dept_raw).strip() if not pd.isna(dept_raw) else ""

        # Safety or EHS get grouped with safety flag
        safety_raw = row.get("Safety", "")
        class_raw = row.get("Class", "")

        safety = _parse_safety(safety_raw, class_raw)
        age_days = _get_wo_age(row.get("Date Created", None))
        priority = _parse_priority(
            row.get("Priority", ""), wo_type=wo_type, safety=safety)

        # Parse due date
        schedule_date_raw = row.get("Sched. Start Date")
        if pd.isna(schedule_date_raw):
            schedule_date = None
        else:
            schedule_date = pd.to_datetime(schedule_date_raw).date()

        # Skip rows with missing essential data
        if not wo_id or duration_hours <= 0 or not trade:
            continue

        # Fix flag (schedule on sched date) for Safety + Preventative maintenance (i.e. EHS pm)
        if type_raw == "Preventive maintenance" and safety:
            fixed = True
        else:
            fixed = False

        work_orders.append(
            WorkOrder(
                id=wo_id,
                description=description,
                duration_hours=duration_hours,
                priority=priority,
                schedule_date=schedule_date,
                trade=trade,
                type=wo_type,
                safety=safety,
                age_days=age_days,
                fixed=fixed,
                num_people=num_people,
                equipment=equipment,
                dept=dept,
            )
        )

    # Persist parsed backlog to JSON for later retrieval
    try:
        base_dir = Path(__file__).resolve().parents[2]
        json_dir = base_dir / "data" / "schedules"
        json_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_dir / "backlog.json"

        payload = []
        for wo in work_orders:
            payload.append(
                {
                    "id": wo.id,
                    "description": wo.description,
                    "duration_hours": wo.duration_hours,
                    "priority": wo.priority,
                    "schedule_date": wo.schedule_date.isoformat() if wo.schedule_date else None,
                    "trade": wo.trade,
                    "type": wo.type,
                    "safety": wo.safety,
                    "age_days": wo.age_days,
                    "fixed": wo.fixed,
                    "num_people": wo.num_people,
                    "equipment": wo.equipment,
                    "dept": wo.dept,
                }
            )

        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        # JSON persistence is best-effort; do not break parsing if it fails
        pass

    return work_orders


def get_backlog_from_json() -> List[WorkOrder]:
    """Load previously parsed work orders from data/json/backlog.json."""
    base_dir = Path(__file__).resolve().parents[2]
    json_path = base_dir / "data" / "schedules" / \
        "backlog" + "_" + date.today().isoformat() + ".json"

    if not json_path.exists():
        return []

    try:
        raw = json_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return []

    work_orders: List[WorkOrder] = []
    for item in data:
        schedule_date_str = item.get("schedule_date")
        if schedule_date_str:
            try:
                schedule_date = date.fromisoformat(schedule_date_str)
            except ValueError:
                schedule_date = None
        else:
            schedule_date = None

        work_orders.append(
            WorkOrder(
                id=item.get("id"),
                description=item.get("description", ""),
                duration_hours=item.get("duration_hours", 0),
                priority=item.get("priority", 0),
                schedule_date=schedule_date,
                trade=item.get("trade", ""),
                type=item.get("type", ""),
                safety=item.get("safety", False),
                age_days=item.get("age_days", 0),
                fixed=item.get("fixed", False),
                num_people=item.get("num_people", 1),
                equipment=item.get("equipment", ""),
                dept=item.get("dept", ""),
            )
        )

    return work_orders


def build_schedule_workbook(schedule: Schedule) -> Workbook:
    from datetime import timedelta

    wb = Workbook()
    ws = wb.active
    ws.title = "Schedule"

    ws.append(
        [
            "work_order_id",
            "num_people",
            "equipment",
            "dept",
            "schedule_date",
            "day_offset",
        ]
    )

    for a in schedule.assignments:
        scheduled_date = schedule.start_date + timedelta(days=a.day_offset)
        ws.append(
            [
                a.work_order_id,
                a.num_people,
                a.equipment,
                a.dept,
                scheduled_date,
                a.day_offset,
            ]
        )

    return wb
