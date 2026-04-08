## Industrial Maintenance Scheduler

This project generates optimized work schedules for an industrial maintenance team using Google OR-Tools, work order backlogs, prioritization rules, and team shift definitions.

### High-level Architecture

- **Backend (Python + FastAPI)**:
  - **Google OR-Tools** CP-SAT solver for daily/weekly schedule optimization.
  - Work order backlog from `.xlsx` (EAM export) or live from EAM REST API via `CloudBacklogClient`.
  - **Shift schedules** stored in `data/shifts.json`; parsed backlog can be cached in `data/json/backlog.json`.
  - REST API: upload backlog, run optimization, download schedule as `.xlsx` or JSON.

- **Web UI (FastAPI + Jinja + FullCalendar)**:
  - **Home** (`/`): Upload backlog `.xlsx`, run **Optimize & Visualize**, view schedule on a calendar, download schedule `.xlsx`.
  - **Shifts** (`/shifts`): Manage trades, shift days, crew size, and hours per shift (CRUD).

- **Future**: Copilot/chatbot integration; AWS deployment (e.g. ECS/Fargate, S3/CloudFront).

### Tech Stack

- **Python 3.11+**
- **ortools** (scheduling), **fastapi** + **uvicorn** (API), **pandas** + **openpyxl** (Excel), **pydantic**, **jinja2**
- **Frontend**: Jinja templates, FullCalendar (calendar), vanilla JS

### Project Layout

- `app/`
  - `main.py` – FastAPI app, routes (optimize, shifts CRUD, health).
  - `models/` – `domain.py` (WorkOrder, Assignment, Schedule), `shift.py` (Shift).
  - `services/` – `optimizer.py` (OR-Tools), `excel_io.py` (backlog/schedule Excel + JSON), `cloud_backlog_client.py` (EAM REST: backlog fetch + work order PATCH), `shift_service.py` (shifts persistence).
  - `utils/` – `date_utils.py` (e.g. next Monday).
  - `templates/` – `index.html`, `shifts.html`.
  - `static/` – JS/CSS assets.
- `data/` – `shifts.json` (shift definitions), `json/backlog.json` (optional cached backlog).
- `samples/` – `EAMExport.xlsx` (sample backlog), `schedule_output.csv` (example output). See `samples/README.md`.
- `debug.py` – Local testing and optimizer-with-Excel runs.
- `requirements.txt`, `pyproject.toml` – Dependencies and Black/Ruff config.

### Sample Data

- **Backlog**: `samples/EAMExport.xlsx` – EAM export format (Work Order, Description, Estimated Hours, Priority, Trade, Type, Safety/Class, etc.). See `samples/README.md` for column details.
- **Shifts**: Define trades and active days in the **Shifts** UI or by editing `data/shifts.json`.

### Quick Start

1. **Create a virtual environment** (recommended):
   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # source .venv/bin/activate   # macOS/Linux
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the server**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   For access from other machines on your network:
   ```bash
   uvicorn app.main:app --reload --port 8000 --host 0.0.0.0
   ```

4. Open **http://127.0.0.1:8000** → choose a backlog `.xlsx` (e.g. `samples/EAMExport.xlsx`) → **Optimize & Visualize** → view calendar and download schedule.

5. Configure **Shifts** at **http://127.0.0.1:8000/shifts** so the optimizer has trades and capacity.

### API Endpoints

- `POST /api/optimize` – Body: `multipart/form-data` with `backlog_file` (.xlsx). Returns JSON schedule.
- `POST /api/optimize/xlsx` – Same input; returns schedule as `.xlsx` attachment.
- `GET /api/shifts`, `GET /api/shifts/{trade}`, `POST /api/shifts`, `PUT /api/shifts/{trade}`, `DELETE /api/shifts/{trade}` – Shifts CRUD.
- `GET /health` – Health check.

### Testing & Debugging

- **Debug script**: `python debug.py` for an interactive menu, or `python debug.py shift` | `excel` | `optimize` | `optimize-excel` | `output` | `all`.
- **IDE**: Use `.vscode/launch.json` (e.g. **Python: FastAPI App**, **Python: Debugger Script (Optimizer Tests)**). Set breakpoints and run with F5.

### Code Formatting

- **Black** (88-char line length) and **Ruff**; config in `pyproject.toml` and `.vscode/settings.json`. Format on save is enabled when the Black Formatter extension is installed.
- Manual format: `black app/`

### EAM REST Integration

`CloudBacklogClient` (`app/services/cloud_backlog_client.py`) connects to the Hexagon EAM REST API for two operations:

- **`fetch_backlog()`** -- POST to the grid endpoint; returns work orders as a `DataFrame`.
- **`patch_eam_schedule_data(wo, schedule)`** -- PATCH a work order's start date back to EAM.

Configuration is via `.env` (see `.env.example`). Required variables:

| Variable | Purpose |
|---|---|
| `INTEGRATION_BASE_URL` | Base URL for all EAM REST calls |
| `BACKLOG_ENDPOINT` | Path appended for backlog grid POST |
| `SCHEDULE_ENDPOINT` | Path appended for work order PATCH |
| `BACKLOG_INTEGRATION_API_KEY` | API key sent as `X-API-Key` header |
| `TENANT_ID` | EAM tenant header |
| `ORGANIZATION` | EAM organization header |
| `GRID_ID` | Grid ID for backlog dataspy |
| `DATASPY_ID` | Dataspy ID for backlog query |

### Next Steps

- Copilot/chatbot API for “what-if” questions and re-optimization.
- Docker image and AWS deployment (ECS/Fargate, S3/CloudFront).
