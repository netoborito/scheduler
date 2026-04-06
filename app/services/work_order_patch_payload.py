"""Merge EAM work-order PATCH templates with ``EamWorkOrderScheduleData`` overrides."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from app.models.eam_schedule import EamWorkOrderScheduleData


def eam_date_block(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    second: int,
    subsecond: int,
    timezone: str,
    qualifier: str,
) -> dict[str, Any]:
    """Build one EAM REST date object (keys match upstream API)."""
    return {
        "YEAR": year,
        "MONTH": month,
        "DAY": day,
        "HOUR": hour,
        "MINUTE": minute,
        "SECOND": second,
        "SUBSECOND": subsecond,
        "TIMEZONE": timezone,
        "qualifier": qualifier,
    }


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge ``patch`` into ``base`` (nested dicts merge; else replace)."""
    out: dict[str, Any] = dict(base)
    for key, val in patch.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def build_work_order_patch_body(
    *,
    schedule: EamWorkOrderScheduleData,
    template_path: Path | str | None = None,
    template: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load a JSON template and merge ``schedule`` datetime overrides."""
    if template_path is None and template is None:
        raise ValueError("template or template_path is required")
    if template_path is not None:
        path = Path(template_path)
        base: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    else:
        base = copy.deepcopy(template)  # type: ignore[arg-type]
    overrides = schedule.to_patch_overrides()
    return deep_merge(base, overrides)


def build_eam_patch_body(
    template_path: Path | str,
    schedule: EamWorkOrderScheduleData,
) -> dict[str, Any]:
    """Load template from ``template_path`` and merge ``schedule`` overrides."""
    return build_work_order_patch_body(
        schedule=schedule,
        template_path=template_path,
    )
