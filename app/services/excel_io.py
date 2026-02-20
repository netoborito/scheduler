from __future__ import annotations

from io import BytesIO
from typing import List
import re

import pandas as pd
from openpyxl import Workbook

from app.models.domain import WorkOrder, Schedule


def _parse_priority(priority_str: str) -> int:
    """Extract priority as integer from first character of priority field.
    
    Examples:
        "1-Critical" -> 1
        "2-Urgent/Scheduled" -> 2
        "3-First Opportunity" -> 3
        "" or blank -> 3 (default)
    """
    if pd.isna(priority_str):
        return 3  # Default priority if blank
    
    priority_str = str(priority_str).strip()
    
    # If empty after stripping, return default
    if not priority_str:
        return 3
    
    # Extract first digit
    match = re.match(r"^(\d+)", priority_str)
    if match:
        return int(match.group(1))
    
    # If no digit found, return default
    return 3


def parse_backlog_from_excel(xlsx_bytes: bytes) -> List[WorkOrder]:
    """Parse work order backlog from Excel file.
    
    Expects EAM export format with columns:
    - Work Order: Work order ID
    - Description: Work order description
    - Estimated Hs: Estimated hours (duration, converted to int - no fractional hours)
    - Priority: Priority text (e.g., "1-Critical", "2-Urgent/Scheduled")
    - Sched Start Date: Scheduled start date (used as due date)
    - Trade: Required trade/resource type for this work order
    """
    buffer = BytesIO(xlsx_bytes)
    df = pd.read_excel(buffer)

    work_orders: List[WorkOrder] = []
    
    for _, row in df.iterrows():
        # EAM Export format column mapping
        wo_id = str(row.get("Work Order", ""))
        description = str(row.get("Description", ""))
        # Convert duration to int (no fractional hours)
        duration_raw = row.get("Estimated Hs", 0.0)
        duration_hours = int(round(float(duration_raw))) if not pd.isna(duration_raw) else 0
        priority_str = row.get("Priority", "")
        priority = _parse_priority(priority_str)
        due_date_raw = row.get("Sched Start Date")
        trade_raw = row.get("Trade", "")
        trade = str(trade_raw).strip() if not pd.isna(trade_raw) else ""
        
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

