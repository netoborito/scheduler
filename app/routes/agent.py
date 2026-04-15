"""Agent-facing API endpoints for LLM/tool integrations."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.excel_io import fetch_backlog
from app.services.gains_service import load_gains, save_gains, validate_gains
from app.services.hints_service import load_hints, save_hints, validate_hint
from app.services.optimizer import DAYS, DEFAULT_OBJECTIVE_GAINS, optimize_schedule
from app.services.preferences_service import (
    load_preferences,
    save_preferences,
    validate_rule,
)
from app.utils.date_utils import get_next_monday

router = APIRouter(prefix="/api/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PreferenceRule(BaseModel):
    match: Dict[str, str]
    set: Dict[str, str]


class PreferencesPayload(BaseModel):
    rules: List[PreferenceRule]


class GainsPayload(BaseModel):
    gains: Dict[str, float]


class HintItem(BaseModel):
    work_order_id: str
    day: str
    trade: str
    scheduled: bool = True


class HintsPayload(BaseModel):
    hints: List[HintItem]


# ---------------------------------------------------------------------------
# Gains endpoints
# ---------------------------------------------------------------------------


@router.get("/gains")
async def get_gains() -> dict:
    """Return current objective gains and their defaults."""
    return {"gains": load_gains(), "defaults": dict(DEFAULT_OBJECTIVE_GAINS)}


@router.put("/gains")
async def put_gains(payload: GainsPayload) -> dict:
    """Update objective gains (partial or full, merged with defaults)."""
    try:
        validate_gains(payload.gains)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    merged = {**DEFAULT_OBJECTIVE_GAINS, **payload.gains}
    save_gains(merged)
    return {"status": "ok", "gains": merged}


# ---------------------------------------------------------------------------
# Preferences endpoints
# ---------------------------------------------------------------------------


@router.get("/preferences")
async def get_preferences() -> dict:
    """Return current optimizer preference rules."""
    return {"rules": load_preferences()}


@router.put("/preferences")
async def put_preferences(payload: PreferencesPayload) -> dict:
    """Replace optimizer preference rules (validates regex patterns)."""
    rules = [r.model_dump() for r in payload.rules]
    for i, rule in enumerate(rules):
        try:
            validate_rule(rule)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Rule {i}: {e}")
    save_preferences(rules)
    return {"status": "ok", "count": len(rules)}


# ---------------------------------------------------------------------------
# Hints endpoints
# ---------------------------------------------------------------------------


@router.get("/hints")
async def get_hints() -> dict:
    """Return current persisted agent hints."""
    hints = load_hints()
    return {
        "hints": [
            {"work_order_id": wo_id, "day": day, "trade": trade, "scheduled": scheduled}
            for wo_id, (day, trade, scheduled) in hints.items()
        ]
    }


@router.put("/hints")
async def put_hints(payload: HintsPayload) -> dict:
    """Replace all agent hints (validates each entry)."""
    converted = {}
    for i, item in enumerate(payload.hints):
        try:
            validate_hint(item.day, item.trade, item.scheduled)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Hint {i}: {e}")
        converted[item.work_order_id] = (item.day, item.trade, item.scheduled)
    save_hints(converted)
    return {"status": "ok", "count": len(converted)}


@router.delete("/hints")
async def delete_hints() -> dict:
    """Clear all persisted agent hints."""
    save_hints({})
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Schedule endpoint
# ---------------------------------------------------------------------------


@router.post("/schedule")
async def post_schedule() -> dict:
    """Run optimizer and return a flat, denormalized schedule for agent iteration."""
    start_date = get_next_monday()
    gains = load_gains()
    hints = load_hints()
    work_orders = fetch_backlog(start_date=start_date)
    schedule = optimize_schedule(
        work_orders=work_orders, start_date=start_date, hints=hints or None,
        objective_gains=gains,
    )

    wo_by_id = {str(wo.id): wo for wo in work_orders}
    assigned_ids: set[str] = set()
    assigned: List[dict] = []
    daily_hours: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for a in schedule.assignments:
        wo = wo_by_id.get(str(a.work_order_id))
        if wo is None:
            continue
        assigned_ids.add(str(wo.id))
        sched_date = start_date + timedelta(days=a.day_offset)
        day_name = DAYS[a.day_offset] if 0 <= a.day_offset < len(DAYS) else str(a.day_offset)
        manhours = wo.duration_hours * wo.num_people
        daily_hours[a.resource_id][day_name] += wo.duration_hours
        assigned.append({
            "work_order_id": str(wo.id),
            "date": sched_date.isoformat(),
            "day_of_week": day_name,
            "trade": wo.trade,
            "description": wo.description,
            "priority": wo.priority,
            "duration_hours": wo.duration_hours,
            "manhours": manhours,
            "type": wo.type,
            "safety": wo.safety,
            "equipment": wo.equipment,
        })

    unassigned = [
        {
            "work_order_id": str(wo.id),
            "trade": wo.trade,
            "priority": wo.priority,
            "duration_hours": wo.duration_hours,
        }
        for wo in work_orders
        if str(wo.id) not in assigned_ids
    ]

    return {
        "start_date": start_date.isoformat(),
        "gains": gains,
        "assigned": assigned,
        "unassigned": unassigned,
        "summary": {
            "total_work_orders": len(work_orders),
            "assigned_count": len(assigned),
            "unassigned_count": len(unassigned),
            "per_shift_daily_hours": {
                trade: dict(days) for trade, days in daily_hours.items()
            },
        },
    }
