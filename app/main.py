from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from pathlib import Path
from io import BytesIO

from .services.excel_io import parse_backlog_from_excel, build_schedule_workbook
from .services.optimizer import optimize_schedule
from .utils.date_utils import get_next_monday
from .models.shift import Shift
from .services.shift_service import (
    add_shift,
    delete_shift,
    get_all_shifts,
    get_shift_by_trade,
    update_shift,
)


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Create static directory if it doesn't exist
STATIC_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Industrial Maintenance Scheduler")

# Only mount static files if directory exists and has content
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
        },
    )


@app.post("/api/optimize")
async def api_optimize(
    backlog_file: UploadFile = File(...),
) -> dict:
    backlog = await backlog_file.read()
    start_date = get_next_monday()
    work_orders = parse_backlog_from_excel(backlog, start_date=start_date)
    schedule = optimize_schedule(work_orders=work_orders, start_date=start_date)
    return {"schedule": schedule.to_api_payload()}


@app.post("/api/optimize/xlsx")
async def api_optimize_xlsx(
    backlog_file: UploadFile = File(...),
) -> StreamingResponse:
    backlog_bytes = await backlog_file.read()
    start_date = get_next_monday()
    work_orders = parse_backlog_from_excel(backlog_bytes, start_date=start_date)
    schedule = optimize_schedule(work_orders=work_orders, start_date=start_date)

    wb = build_schedule_workbook(schedule)
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="schedule.xlsx"'},
    )


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
