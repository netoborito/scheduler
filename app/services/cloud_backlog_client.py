"""HTTP client for the cloud work-order backlog (REST / grid endpoint)."""

from __future__ import annotations

import json
import os
from datetime import timedelta, datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from app.config import BacklogIntegrationSettings, get_backlog_integration_settings
from app.models.domain import Assignment, Schedule, WorkOrder


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
        "REQUEST_TYPE": "LIST.HEAD_DATA.STORED",
    }


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


def _parse_eam_payload_to_dataframe(data: dict[str, Any]) -> pd.DataFrame:
    """Build a DataFrame from json payload"""
    grid = data["Result"]["ResultData"]["GRID"]
    rows = grid["DATA"]["ROW"]
    columns = [f["label"] for f in grid["FIELDS"]["FIELD"]]
    matrix = [
        [str(c.get("value", "") if isinstance(c, dict) else (c or "")) for c in row.get("D", [])]
        for row in rows
    ]
    return pd.DataFrame(matrix, columns=columns)


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
        cfg = self._settings
        return f"{cfg.rest_url}{cfg.schedule_endpoint}/{wo_id}%23AZP%20MOORESBORO"

    def _build_schedule_data_patch_payload(
        self,
        dateblock: dict[str, Any],
        wo_id: int,
    ) -> dict[str, Any]:
        return {
            "WORKORDERID": {
                "JOBNUM": wo_id,
            },
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
            "YEAR": year_ux,
            "MONTH": schedule_date.month,
            "DAY": schedule_date.day,
            "HOUR": 7,
            "MINUTE": 0,
            "SECOND": 0,
            "SUBSECOND": 0,
            "TIMEZONE": "-0500",
            "qualifier": "OTHER",
        }

        # build patch body
        body = self._build_schedule_data_patch_payload(
            dateblock=dateblock,
            wo_id=wo.id,
        )

        # patch work order
        url = self._work_order_url(wo.id)
        print(
            json.dumps(
                {
                    "method": "PATCH",
                    "url": url,
                    "headers": self._headers(),
                    "body": body,
                },
                indent=2,
            )
        )
        data, response = self._request_json_with_response("PATCH", url, body)

        return data, response

    def fetch_backlog(self) -> pd.DataFrame:
        """POST and return the backlog as a formatted DataFrame, or raise ``CloudBacklogError``."""
        cfg = self._settings
        url = self._settings.rest_url + self._settings.backlog_endpoint
        body = _grid_list_request_body(cfg)

        data, response = self._request_json_with_response("POST", url, body)
        df = _parse_eam_payload_to_dataframe(data)
        df = _format_backlog_df(df)

        debug_csv = os.environ.get("BACKLOG_DEBUG_CSV", "").strip()
        if debug_csv:
            dest = Path(debug_csv)
            dest.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(dest, index=False)

        return df
