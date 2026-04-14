from fastapi import FastAPI, Form, HTTPException, Body
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from pathlib import Path
from io import BytesIO
from datetime import date
from typing import List, Optional
import json

from .services.excel_io import fetch_backlog, build_schedule_workbook
from .services.optimizer import optimize_schedule
from .utils.date_utils import get_next_monday
from .models.shift import Shift
from .models.domain import Schedule, Assignment, WorkOrder
from .services.shift_service import (
    add_shift,
    delete_shift,
    get_all_shifts,
    get_shift_by_trade,
    update_shift,
)
from pydantic import BaseModel

from .config import load_app_env
from .routes.agent import router as agent_router


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Create static directory if it doesn't exist
STATIC_DIR.mkdir(exist_ok=True)

load_app_env()

app = FastAPI(title="Industrial Maintenance Scheduler")
app.include_router(agent_router)

# Only mount static files if directory exists and has content
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    # initialize default start date and shifts
    default_start = get_next_monday()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "default_start_date": default_start.isoformat(),
            "default_start_date_display": default_start.strftime("%m/%d/%Y"),
        },
    )


@app.post("/api/optimize")
async def api_optimize(
    hints_json: Optional[str] = Form(None),
) -> dict:

    # load hints if provided
    hints = None

    if hints_json:
        parsed_hints = json.loads(hints_json)
        hints = {
            str(wo_id): (str(values[0]), str(values[1]), bool(values[2]))
            for wo_id, values in parsed_hints.items()
            if isinstance(values, list) and len(values) >= 3
        }

    start_date = get_next_monday()

    work_orders = fetch_backlog(start_date=start_date)

    # optimize schedule
    schedule = optimize_schedule(
        work_orders=work_orders, start_date=start_date, hints=hints)

    # print result to console and return schedule json
    print("api_optimize: work_orders", len(work_orders))
    print("api_optimize: assignments", len(schedule.assignments))

    # build shift -> color map and availability from configured shifts
    shifts = get_all_shifts()
    shift_colors = {
        s.trade: getattr(s, "color", "") for s in shifts if getattr(s, "color", "")
    }
    shift_availability = [
        {
            "trade": s.trade,
            "shift_duration_hours": s.shift_duration_hours,
            "technicians_per_crew": getattr(s, "technicians_per_crew", 1),
            "monday": s.monday,
            "tuesday": s.tuesday,
            "wednesday": s.wednesday,
            "thursday": s.thursday,
            "friday": s.friday,
            "saturday": s.saturday,
            "sunday": s.sunday,
        }
        for s in shifts
    ]

    response_payload = {
        "schedule": schedule.to_api_payload(),
        "work_orders": [
            {
                "id": wo.id,
                "description": wo.description,
                "duration_hours": wo.duration_hours,
                "equipment": wo.equipment,
                "priority": wo.priority,
                "schedule_date": wo.schedule_date.isoformat()
                if getattr(wo, "schedule_date", None)
                else None,
                "trade": wo.trade,
                "type": wo.type,
                "safety": wo.safety,
                "age_days": wo.age_days,
                "num_people": getattr(wo, "num_people", 1),
            }
            for wo in work_orders
        ],
        "shift_colors": shift_colors,
        "shift_availability": shift_availability,
    }
    return response_payload


@app.post("/api/optimize/xlsx")
async def api_optimize_xlsx(payload: dict = Body(...)) -> StreamingResponse:
    schedule_payload = payload.get("latestSchedule")
    work_orders_payload = payload.get("latestWorkOrders")
    if not isinstance(schedule_payload, dict) or not isinstance(work_orders_payload, list):
        raise HTTPException(
            status_code=400,
            detail="Expected JSON payload with latestSchedule and latestWorkOrders.",
        )

    start_date_raw = schedule_payload.get("start_date")
    if not start_date_raw:
        raise HTTPException(
            status_code=400,
            detail="latestSchedule.start_date is required.",
        )

    assignments = [
        Assignment(
            work_order_id=str(a.get("work_order_id", "")),
            day_offset=int(a.get("day_offset", 0)),
            resource_id=str(a.get("resource_id", "")),
        )
        for a in (schedule_payload.get("assignments") or [])
    ]
    schedule = Schedule(
        assignments=assignments,
        horizon_days=int(schedule_payload.get("horizon_days", 7)),
        start_date=date.fromisoformat(start_date_raw),
    )

    work_orders: list[WorkOrder] = []
    for item in work_orders_payload:
        schedule_date_raw = item.get("schedule_date")
        schedule_date = date.fromisoformat(
            schedule_date_raw) if schedule_date_raw else None
        work_orders.append(
            WorkOrder(
                id=str(item.get("id", "")),
                description=str(item.get("description", "")),
                duration_hours=float(item.get("duration_hours", 0.5)),
                priority=int(item.get("priority", 5)),
                schedule_date=schedule_date,
                trade=str(item.get("trade", "")),
                type=str(item.get("type", "")),
                safety=bool(item.get("safety", False)),
                age_days=int(item.get("age_days", 0)),
                fixed=bool(item.get("fixed", False)),
                num_people=int(item.get("num_people", 1)),
                equipment=str(item.get("equipment", "")),
                dept=str(item.get("dept", "")),
            )
        )

    wb = build_schedule_workbook(schedule, work_orders=work_orders)
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="schedule.xlsx"'},
    )


class ScheduleHintItem(BaseModel):
    work_order_id: str
    schedule_date: date
    trade: str
    hint: int


@app.post("/api/schedule/hints")
async def api_save_schedule_hints(items: List[ScheduleHintItem]) -> dict:
    """Persist UI-modified schedule hints for optimizer debugging/analysis."""
    debug_dir = BASE_DIR.parent / "data" / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / "schedule_hints.json"

    payload = [item.model_dump() for item in items]
    # Ensure dates are serialized as ISO strings
    for entry in payload:
        if isinstance(entry.get("schedule_date"), date):
            entry["schedule_date"] = entry["schedule_date"].isoformat()

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"status": "ok", "count": len(payload), "path": str(path)}


@app.get("/shifts", response_class=HTMLResponse)
async def shifts_page(request: Request) -> HTMLResponse:
    """Shifts management page."""
    return templates.TemplateResponse("shifts.html", {"request": request})


# Shift CRUD API endpoints
@app.get("/api/shifts")
async def api_get_shifts() -> dict:
    """Get all shifts."""
    shifts = get_all_shifts()
    return {"shifts": [shift.to_dict() for shift in shifts]}


@app.get("/api/shifts/{trade:path}")
async def api_get_shift(trade: str) -> dict:
    """Get a specific shift by trade (trade may contain slashes, e.g. NC-E/I)."""
    shift = get_shift_by_trade(trade)
    if not shift:
        raise HTTPException(
            status_code=404, detail=f"Shift with trade '{trade}' not found"
        )
    return {"shift": shift.to_dict()}


@app.post("/api/shifts")
async def api_create_shift(
    trade: str = Form(...),
    shift_duration_hours: int = Form(...),
    monday: bool = Form(False),
    tuesday: bool = Form(False),
    wednesday: bool = Form(False),
    thursday: bool = Form(False),
    friday: bool = Form(False),
    saturday: bool = Form(False),
    sunday: bool = Form(False),
    technicians_per_crew: int = Form(1),
    color: str = Form(""),
) -> dict:
    """Create a new shift."""
    shift = Shift(
        trade=trade,
        shift_duration_hours=shift_duration_hours,
        monday=monday,
        tuesday=tuesday,
        wednesday=wednesday,
        thursday=thursday,
        friday=friday,
        saturday=saturday,
        sunday=sunday,
        technicians_per_crew=technicians_per_crew,
        color=color,
    )
    try:
        add_shift(shift)
        return {"message": "Shift created successfully", "shift": shift.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/shifts/{trade:path}")
async def api_update_shift(
    trade: str,
    shift_duration_hours: int = Form(...),
    monday: bool = Form(False),
    tuesday: bool = Form(False),
    wednesday: bool = Form(False),
    thursday: bool = Form(False),
    friday: bool = Form(False),
    saturday: bool = Form(False),
    sunday: bool = Form(False),
    technicians_per_crew: int = Form(1),
    color: str = Form(""),
) -> dict:
    """Update an existing shift."""
    updated_shift = Shift(
        trade=trade,
        shift_duration_hours=shift_duration_hours,
        monday=monday,
        tuesday=tuesday,
        wednesday=wednesday,
        thursday=thursday,
        friday=friday,
        saturday=saturday,
        sunday=sunday,
        technicians_per_crew=technicians_per_crew,
        color=color,
    )
    try:
        update_shift(trade, updated_shift)
        return {
            "message": "Shift updated successfully",
            "shift": updated_shift.to_dict(),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/shifts/{trade:path}")
async def api_delete_shift(trade: str) -> dict:
    """Delete a shift."""
    try:
        delete_shift(trade)
        return {"message": f"Shift '{trade}' deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def create_app() -> FastAPI:
    return app
