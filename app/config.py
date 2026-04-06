"""Backlog REST integration settings from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_app_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True)
class BacklogIntegrationSettings:
    rest_url: str
    api_key: str
    http_timeout_seconds: int
    tenant_id: str
    organization: str
    grid_id: int
    dataspy_id: int
    #: Base URL for work order REST calls; final path is ``{base}/workorders/{wo_id}``.
    work_order_api_base_url: str
    #: Path to JSON template for ``patch_eam_schedule_data`` (``EAM_PATCH_TEMPLATE_PATH``); required for that API.
    eam_patch_template_path: str


def _build_rest_url() -> str:
    explicit = os.environ.get("BACKLOG_REST_URL", "").strip()
    if explicit:
        return explicit
    base = os.environ.get("BACKLOG_INTEGRATION_BASE_URL",
                          "").strip().rstrip("/")
    path = os.environ.get("BACKLOG_BACKLOG_PATH", "").strip().lstrip("/")
    if base and path:
        return f"{base}/{path}"
    if base:
        return base
    return ""


def get_backlog_integration_settings() -> BacklogIntegrationSettings:
    timeout_raw = os.environ.get("BACKLOG_HTTP_TIMEOUT_SECONDS", "30").strip()
    try:
        timeout = int(timeout_raw) if timeout_raw else 30
    except ValueError:
        timeout = 30
    return BacklogIntegrationSettings(
        rest_url=_build_rest_url(),
        api_key=os.environ.get("BACKLOG_INTEGRATION_API_KEY", "").strip(),
        http_timeout_seconds=timeout,
        tenant_id=os.environ.get("TENANT_ID", "").strip(),
        organization=os.environ.get("ORGANIZATION", "").strip(),
        grid_id=int(os.environ.get("GRID_ID", "")),
        dataspy_id=int(os.environ.get("DATASPY_ID", "")),
        work_order_api_base_url=os.environ.get(
            "WORK_ORDER_API_BASE_URL", ""
        ).strip().rstrip("/"),
        eam_patch_template_path=os.environ.get(
            "EAM_PATCH_TEMPLATE_PATH", ""
        ).strip(),
    )
