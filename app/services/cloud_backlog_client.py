"""HTTP client for EAM Rest endpoints"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from app.config import BacklogIntegrationSettings, get_backlog_integration_settings
from app.models.domain import Schedule, WorkOrder


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Backlog helpers
# ---------------------------------------------------------------------------


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


def _parse_eam_payload_to_dataframe(data: dict[str, Any]) -> pd.DataFrame:
    """Build a DataFrame from json payload"""
    grid = data["Result"]["ResultData"]["DATARECORD"]
    columns = [f["FIELDLABEL"] for f in grid[0]["DATAFIELD"]]
    matrix = [[f["FIELDVALUE"] for f in row["DATAFIELD"]] for row in grid]
    df = pd.DataFrame(matrix, columns=columns)
    df = df.loc[:, ~df.columns.duplicated(keep="last")]
    return df


# ---------------------------------------------------------------------------
# PATCH helper
# ---------------------------------------------------------------------------


def _generate_date_block(schedule_start_date: date, day_offset: int) -> dict[str, Any]:
    """Build EAM date block for a work order's scheduled date."""
    schedule_date = schedule_start_date + timedelta(days=day_offset)
    year_ux = int(
        datetime(schedule_date.year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
    )
    return {
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


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


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
        self, method: str, url: str, json_body: dict[str, Any] | None = None
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
            raise CloudBacklogError(f"EAM request failed: {e}") from e

        if not response.is_success:
            snippet = (response.text or "")[:500]
            raise CloudBacklogError(
                f"EAM HTTP {response.status_code}: {snippet}",
                response=response,
            )
        try:
            data = response.json()
        except ValueError as e:
            raise CloudBacklogError(
                "EAM response is not valid JSON",
                response=response,
            ) from e
        return data, response

    # -- Backlog fetch ------------------------------------------------------

    def fetch_backlog(self) -> pd.DataFrame:
        """POST and return the backlog as a formatted DataFrame, or raise ``CloudBacklogError``."""
        cfg = self._settings
        body = _grid_list_request_body(cfg)
        url = f"{cfg.rest_url}{cfg.backlog_endpoint}"

        data, _ = self._request_json_with_response("POST", url, body)
        df = _parse_eam_payload_to_dataframe(data)

        return df

    # -- Work order PATCH ---------------------------------------------------

    def _work_order_url(self, wo_id: str | int) -> str:
        cfg = self._settings
        return f"{cfg.rest_url}{cfg.schedule_endpoint}/{wo_id}%23AZP%20MOORESBORO"

    def _build_schedule_data_patch_payload(
        self,
        dateblock: dict[str, Any],
        wo_id: int,
        trade: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "WORKORDERID": {
                "JOBNUM": wo_id,
            },
            "STARTDATE": dateblock,
        }
        if trade:
            payload["ASSIGNEDTO"] = trade  # TODO: replace with actual EAM field name
        return payload

    def patch_eam_schedule_data(
        self,
        wo: WorkOrder,
        schedule: Schedule,
    ) -> httpx.Response:
        """PATCH work order schedule data and trade assignment to EAM."""
        assignment = next(a for a in schedule.assignments if a.work_order_id == str(wo.id))
        dateblock = _generate_date_block(schedule.start_date, assignment.day_offset)
        body = self._build_schedule_data_patch_payload(
            dateblock=dateblock,
            wo_id=wo.id,
            trade=assignment.resource_id,
        )
        url = self._work_order_url(wo.id)

        _, response = self._request_json_with_response("PATCH", url, body)

        return response.json()
