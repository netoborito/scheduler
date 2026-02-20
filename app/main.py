from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from pathlib import Path
from io import BytesIO

from .services.excel_io import parse_backlog_from_excel, build_schedule_workbook
from .services.optimizer import optimize_schedule
from .utils.date_utils import get_next_monday


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
    work_orders = parse_backlog_from_excel(backlog)
    start_date = get_next_monday()
    schedule = optimize_schedule(
        work_orders=work_orders, 
        start_date=start_date
    )
    return {"schedule": schedule.to_api_payload()}


@app.post("/api/optimize/xlsx")
async def api_optimize_xlsx(
    backlog_file: UploadFile = File(...),
) -> StreamingResponse:
    backlog_bytes = await backlog_file.read()
    work_orders = parse_backlog_from_excel(backlog_bytes)
    start_date = get_next_monday()
    schedule = optimize_schedule(
        work_orders=work_orders, 
        start_date=start_date
    )

    wb = build_schedule_workbook(schedule)
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="schedule.xlsx"'},
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def create_app() -> FastAPI:
    return app

