"""HTTP client for the cloud work-order backlog (REST / grid endpoint)."""

from __future__ import annotations

import json
import os
from datetime import timedelta, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pandas as pd

from app.config import BacklogIntegrationSettings, get_backlog_integration_settings
from app.models.domain import Assignment, Schedule, WorkOrder

# CSV column names in order; index i matches EAM row D[i].value. Edit to match your grid.
BACKLOG_CSV_COLUMNS: list[str] = [
    # "0": "Equipment",
    # "1": "Department",
    # "2": "Type",
    # "3": "EHS",
    # "4": "code",
    # "5": "Status",
    # "6": "Priority",
    # "7": "Scheduled Start Date",
    # "8": "Organization",
    # "9": "WO_ID",
    # "10": "Assigned To",
    # "11": "Trade",
    # "12": "Hours",
    # "13": "Persons Required",
    # "14": "Organization",
    # "15": "code",
    # "16": "Description",
    # "17": "Safety",
    # "18": "Original PM Due Date",
    # "19": "blank",
    # "20": "blank",
    # "21": "blank",
    # "22": "blank",
    # "23": "blank",
    # "24": "blank",
    # "25": "blank",
    # "26": "unknown number",
    # "27": "A/S",
    # "28": "Date Created",
    # "29": "blank",
    # "30": "Equipment Description"
]


def _assignment_for_work_order(wo: WorkOrder, schedule: Schedule) -> Assignment:
    """Prefer assignment whose ``work_order_id`` matches ``wo.id``; else index ``wo.id``."""
    for a in schedule.assignments:
        if a.work_order_id == str(wo.id):
            return a
    if 0 <= wo.id < len(schedule.assignments):
        return schedule.assignments[wo.id]
    raise CloudBacklogError(
        f"No schedule assignment for work order id {wo.id} "
        f"(list length {len(schedule.assignments)})"
    )


class CloudBacklogError(Exception):
    """Raised when the backlog request fails (network, HTTP status, or non-JSON body)."""

    def __init__(
        self,
        message: str,
        *,
        response: httpx.Response | None = None,
    ) -> None:
        super().__init__(message)
        self.response = response


def _grid_list_request_body(cfg: BacklogIntegrationSettings) -> dict[str, Any]:
    """POST body for EAM grid backlog list fetch."""
    return {
        "GRID": {
            "GRID_NAME": "WSJOBS",
            "USER_FUNCTION_NAME": "WSJOBS",
            "GRID_ID": cfg.grid_id,
            "NUMBER_OF_ROWS_FIRST_RETURNED": 10000,
            "CURSOR_POSITION": 0,
            "LOCALIZE_RESULT": "TRUE",
        },
        "GRID_TYPE": {"TYPE": "LIST"},
        "DATASPY": {"DATASPY_ID": cfg.dataspy_id},
        "REQUEST_TYPE": "LIST.DATA_ONLY.STORED",
    }


def _extract_eam_grid_rows(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Return GRID.DATA.ROW list from EAM AddResponse-shaped JSON, or None if absent."""
    result = payload.get("Result")
    if not isinstance(result, dict):
        return None
    rd = result.get("ResultData")
    if not isinstance(rd, dict):
        return None
    grid = rd.get("GRID")
    if not isinstance(grid, dict):
        return None
    data = grid.get("DATA")
    if not isinstance(data, dict):
        return None
    rows = data.get("ROW")
    if rows is None:
        return None
    if isinstance(rows, dict):
        return [rows]
    if isinstance(rows, list):
        return rows
    return None


def _cell_values_from_row(row: dict[str, Any]) -> tuple[Any, list[str]]:
    rid = row.get("id")
    cells = row.get("D") or []
    values: list[str] = []
    for cell in cells:
        if isinstance(cell, dict):
            values.append("" if cell.get("value") is None else str(cell["value"]))
        else:
            values.append("" if cell is None else str(cell))
    return rid, values


def _parse_eam_payload_to_dataframe(
    data: dict[str, Any],
    *,
    response: httpx.Response | None = None,
) -> pd.DataFrame:
    """Build a DataFrame from EAM grid rows or raise ``CloudBacklogError``."""
    if not BACKLOG_CSV_COLUMNS:
        raise CloudBacklogError(
            "BACKLOG_CSV_COLUMNS is empty",
            response=response,
        )
    rows = _extract_eam_grid_rows(data)

    if not rows:
        raise CloudBacklogError(
            "Backlog response has no EAM grid rows",
            response=response,
        )
    n = len(BACKLOG_CSV_COLUMNS)
    matrix: list[list[str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        _rid, vals = _cell_values_from_row(row)
        matrix.append((vals + [""] * n)[:n])
    if not matrix:
        raise CloudBacklogError(
            "Backlog response has no usable grid rows",
            response=response,
        )
    return pd.DataFrame(matrix, columns=list(BACKLOG_CSV_COLUMNS))


def _format_backlog_df(df: pd.DataFrame) -> pd.DataFrame:
    """Light formatting on string cells (e.g. strip whitespace)."""
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].map(lambda x: x.strip() if isinstance(x, str) else x)
    return out


class CloudBacklogClient:
    """EAM HTTP helper: backlog grid fetch and work order PATCH."""

    def __init__(
        self,
        settings: BacklogIntegrationSettings | None = None,
    ) -> None:
        self._settings = settings or get_backlog_integration_settings()

    def _headers(self) -> dict[str, str]:
        cfg = self._settings
        return {
            "accept": "application/json",
            "tenant": cfg.tenant_id,
            "organization": cfg.organization,
            "X-API-Key": cfg.api_key,
            "Content-Type": "application/json",
        }

    def _request_json_with_response(
        self, method: str, url: str, json_body: dict[str, Any]
    ) -> tuple[Any, httpx.Response]:
        cfg = self._settings
        try:
            with httpx.Client(timeout=cfg.http_timeout_seconds) as client:
                response = client.request(
                    method,
                    url,
                    headers=self._headers(),
                    json=json_body,
                )
        except httpx.RequestError as e:
            raise CloudBacklogError(f"Backlog request failed: {e}") from e

        if not response.is_success:
            snippet = (response.text or "")[:500]
            raise CloudBacklogError(
                f"Backlog HTTP {response.status_code}: {snippet}",
                response=response,
            )
        try:
            data = response.json()
        except ValueError as e:
            raise CloudBacklogError(
                "Backlog response is not valid JSON",
                response=response,
            ) from e
        return data, response

    def _work_order_url(self, wo_id: str | int) -> str:
        """Build PATCH URL from ``SCHEDULE_ENDPOINT`` (and optionally ``rest_url``).

        If ``schedule_endpoint`` is an absolute URL (http/https), it is treated as the
        collection base (should usually end with ``/``); the work order id is appended.
        Otherwise it is a path suffix joined after ``rest_url`` with slashes.
        """
        cfg = self._settings
        path_id = quote(str(wo_id), safe="")
        sched = (cfg.schedule_endpoint or "").strip()
        if not sched:
            raise CloudBacklogError(
                "SCHEDULE_ENDPOINT is not configured in the environment"
            )
        if sched.startswith(("http://", "https://")):
            base = sched.rstrip("/")
            return f"{base}/{path_id}"
        rest = (cfg.rest_url or "").strip().rstrip("/")
        if not rest:
            raise CloudBacklogError(
                "BACKLOG_REST_URL / rest_url is not configured "
                "for relative SCHEDULE_ENDPOINT"
            )
        mid = sched.strip("/")
        return f"{rest}/{mid}/{path_id}"

    def _build_schedule_data_patch_payload(
        self,
        dateblock: dict[str, Any],
        wo_id: int,
    ) -> dict[str, Any]:
        return {
            "WORKORDERID": {
                "JOBNUM": wo_id,
            },
            "STATUS": {"STATUSCODE": "R"},
            "DEPARTMENTID": {"DEPARTMENTCODE": "*"},
            "FIXED": "V",
            "STARTDATE": dateblock,
        }

    def patch_eam_schedule_data(
        self,
        wo: WorkOrder,
        schedule: Schedule,
    ) -> Any:
        """PATCH work order schedule data to EAM."""
        assignment = _assignment_for_work_order(wo, schedule)
        schedule_date = schedule.start_date + timedelta(days=assignment.day_offset)

        # put schedule date in desired format
        year = datetime(schedule_date.year, 1, 1, tzinfo=timezone.utc)
        year_ux = int(year.timestamp() * 1000)

        dateblock = {
            "year": year_ux,
            "month": schedule_date.month,
            "day": schedule_date.day,
            "hour": 7,
            "minute": 0,
            "second": 0,
            "subsecond": 0,
            "timezone": "UTC",
            "qualifier": "FROM",
        }

        # build patch body
        body = self._build_schedule_data_patch_payload(
            dateblock=dateblock,
            wo_id=wo.id,
        )

        # patch work order
        url = self._work_order_url(wo.id)
        data, response = self._request_json_with_response("PATCH", url, body)

        return data, response

    def fetch_backlog(self) -> pd.DataFrame:
        """POST and return the backlog as a formatted DataFrame, or raise ``CloudBacklogError``."""
        cfg = self._settings
        url = self._settings.rest_url + self._settings.backlog_endpoint
        body = _grid_list_request_body(cfg)

        data, response = self._request_json_with_response("POST", url, body)
        df = _parse_eam_payload_to_dataframe(data, response=response)
        df = _format_backlog_df(df)

        debug_csv = os.environ.get("BACKLOG_DEBUG_CSV", "").strip()
        if debug_csv:
            dest = Path(debug_csv)
            dest.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(dest, index=False)

        return df
