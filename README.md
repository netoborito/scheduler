## Industrial Maintenance Scheduler

This project generates optimized work schedules for an industrial maintenance team using Google OR-Tools, work order backlogs, prioritization rules, and team shift definitions.

### High-level Architecture

- **Optimizer backend (Python + FastAPI)**:
  - Uses **Google OR-Tools** CP-SAT/linear solver to construct daily/weekly schedules.
  - Imports **work order backlog** from `.xlsx` files (e.g., via `pandas` / `openpyxl`).
  - Persists and reads:
    - **Prioritization rules** (e.g., criticality, due dates, penalties).
    - **Shift schedules** (teams, skills, availability).
  - Exposes REST endpoints to:
    - Upload backlog/parameters.
    - Trigger schedule optimization.
    - Download schedule as `.xlsx`.

- **Web application (FastAPI templates or React SPA)**:
  - Simple UI for testing and demo:
    - Upload backlog `.xlsx`.
    - Configure basic rules and shifts (initially via JSON or form fields).
    - Visualize the resulting schedule on a **calendar-style view** (e.g., by day and maintainer/resource).
    - Download the schedule as `.xlsx`.

- **Copilot / Chatbot integration (future step)**:
  - A thin API layer so Copilot (or other chatbots) can:
    - Upload backlog files and parameters.
    - Ask "what-if" questions and request re-optimization.
    - Apply interactive edits (swap jobs, move work orders, lock assignments).

- **AWS deployment (future step)**:
  - Containerized backend (Docker) deployed to **AWS ECS/Fargate** or **AWS App Runner**.
  - Static frontend hosted via **S3 + CloudFront** or served by the backend.
  - Uses AWS services for file storage and configuration (e.g., S3, SSM Parameter Store) as needed.

### Data Flow (Conceptual)

1. **Input**:
   - User provides **work order backlog** in `.xlsx` format.
   - Prioritization rules and **shift schedules** are persisted in the application (DB or config files). For the first version, these can be stored as JSON or in a lightweight DB (e.g., SQLite).

2. **Optimization**:
   - Backend converts work orders, rules, and shifts into an OR-Tools model.
   - Objective examples:
     - Minimize late/overdue work order penalties.
     - Respect shift availability and skills.
     - Balance workload across maintainers.
   - Produces an assignment of work orders to:
     - Specific maintainer/resource.
     - Date and time (slot within a shift).

3. **Output**:
   - **`.xlsx` schedule**: tabular representation (e.g., row per assignment with dates, person, and work order).
   - **Visual calendar** in the web UI for interactive inspection.

4. **Interactive refinement via chatbot (Copilot)**:
   - User interacts with a chatbot that:
     - Reads the current schedule state from the backend.
     - Applies modifications (e.g., pinning tasks, moving tasks).
     - Requests a re-run of the optimization respecting those constraints.

### Tech Stack (Initial Recommendation)

- **Language**: Python 3.11+
- **Core libraries**:
  - `ortools` (Google OR-Tools).
  - `fastapi` (backend API).
  - `uvicorn` (ASGI server).
  - `pydantic` (data validation).
  - `pandas` + `openpyxl` (Excel I/O).
- **Frontend**:
  - Start with FastAPI + Jinja templates and a JS calendar library (e.g., FullCalendar) for faster initial integration.
  - Optionally evolve into a separate SPA (React/Vue) if/when needed.

### Project Layout (Proposed)

- `app/`
  - `main.py` – FastAPI entrypoint, routes.
  - `models/` – Pydantic models for work orders, shifts, rules, schedules.
  - `services/`
    - `optimizer.py` – OR-Tools model construction and solve logic.
    - `excel_io.py` – Read/write `.xlsx` for backlog and schedule.
  - `routes/` – API endpoints for upload, optimize, download, etc.
  - `templates/` – HTML templates for web UI.
  - `static/` – JS/CSS assets (including calendar JS).
- `tests/` – Unit and integration tests.
- `requirements.txt` – Python dependencies.
- `Dockerfile` – For AWS deployment.

### Sample Data

A sample backlog file (`samples/EAMExport.xlsx`) is included for testing. The parser automatically detects EAM export format and maps columns appropriately. See `samples/README.md` for details.

### Quick Start

1. Install dependencies: `pip install -r requirements.txt`
2. **Install Black formatter extension** in Cursor/VS Code:
   - Open Extensions (Ctrl+Shift+X)
   - Search for "Black Formatter" by Microsoft
   - Install it
3. Start the server: `python -m uvicorn app.main:app --reload --port 8000`
4. Open `http://127.0.0.1:8000` in your browser
5. Upload `samples/EAMExport.xlsx` or your own backlog file

### Code Formatting

The project is configured to automatically format Python code according to PEP 8 on save:
- **Black formatter** is configured with 88-character line length
- Formatting runs automatically when you save any `.py` file
- Configuration is in `.vscode/settings.json` and `pyproject.toml`

To manually format all files:
```bash
black app/
```

### Next Steps

- Implement a **minimal vertical slice**:
  - Upload backlog `.xlsx` → simple OR-Tools model → schedule output as `.xlsx` + basic calendar view.
- Then:
  - Expand prioritization rules and shift modeling.
  - Add endpoints and conventions for Copilot integration on AWS.

