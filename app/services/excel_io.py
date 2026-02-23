from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from typing import List, Optional
import re

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


def _parse_safety(value) -> bool:
    """Coerce Excel/string value to boolean for Safety column.
    Accepts: True/False, 1/0, Yes/No, Y/N (case-insensitive).
    """
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    return s in ("yes", "y", "1", "true")


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
    filtered = filtered.drop(columns=["Equipment Description"], errors="ignore")

    if "Status" in filtered.columns:
        filtered = filtered[filtered["Status"] == "Open - Ready to Schedule"]

    filtered["Sched Start Date"] = pd.to_datetime(
        filtered["Sched Start Date"], errors="coerce"
    )

    end_date = start_date + timedelta(days=horizon_days)
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)

    # Remove PMs beyond the scheduling horizon
    beyond_horizon_PMs = (filtered.get("Type") == "Preventive maintenance") & (
        filtered["Sched Start Date"] > pd.Timestamp(start_ts) + timedelta(days=7)
    )
    filtered = filtered[~beyond_horizon_PMs]

    # Keep: no date (NaT) or date in [start_date, end_date)
    current_wo_omitted = filtered["Sched Start Date"].isna() | (
        (filtered["Sched Start Date"] < start_ts)
        & (filtered["Sched Start Date"] >= end_ts - timedelta(days=7))
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
            int(round(float(duration_raw))) if not pd.isna(duration_raw) else 0
        )
        priority_str = row.get("Priority", "")
        due_date_raw = row.get("Sched Start Date")
        trade_raw = row.get("Trade", "")
        trade = str(trade_raw).strip() if not pd.isna(trade_raw) else ""
        type_raw = row.get("Type", "")
        wo_type = str(type_raw).strip() if not pd.isna(type_raw) else ""

        safety = _parse_safety(row.get("Safety", False))
        age_days = _get_wo_age(row.get("Creation Date", None))
        priority = _parse_priority(priority_str, wo_type=wo_type, safety=safety)

        # Parse due date
        if pd.isna(due_date_raw):
            due_date = None
        else:
            due_date = pd.to_datetime(due_date_raw).date()

        # Skip rows with missing essential data
        if not wo_id or duration_hours <= 0 or not trade:
            continue

        work_orders.append(
            WorkOrder(
                id=wo_id,
                description=description,
                duration_hours=duration_hours,
                priority=priority,
                due_date=due_date,
                trade=trade,
                type=wo_type,
                safety=safety,
                age_days=age_days,
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
            "resource_id",
            "scheduled_date",
            "day_offset",
        ]
    )

    for a in schedule.assignments:
        scheduled_date = schedule.start_date + timedelta(days=a.day_offset)
        ws.append(
            [
                a.work_order_id,
                a.resource_id,
                scheduled_date,
                a.day_offset,
            ]
        )

    return wb
