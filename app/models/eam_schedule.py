"""EAM work-order PATCH payload: date/time blocks attached to a schedule work-order view."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EamDateTimeBlock:
    """Single EAM REST date value (CREATEDDATE, REPORTED, TARGETDATE, etc.)."""

    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int
    subsecond: int
    timezone: str
    qualifier: str

    def to_eam_dict(self) -> dict[str, Any]:
        return {
            "YEAR": self.year,
            "MONTH": self.month,
            "DAY": self.day,
            "HOUR": self.hour,
            "MINUTE": self.minute,
            "SECOND": self.second,
            "SUBSECOND": self.subsecond,
            "TIMEZONE": self.timezone,
            "qualifier": self.qualifier,
        }


_EAM_SCHEDULE_DATE_KEYS: tuple[tuple[str, str], ...] = (
    ("createddate", "CREATEDDATE"),
    ("reported", "REPORTED"),
    ("targetdate", "TARGETDATE"),
    ("schedend", "SCHEDEND"),
    ("requested_start", "REQUESTEDSTART"),
    ("requested_end", "REQUESTEDEND"),
)


@dataclass
class EamWorkOrderScheduleData:
    """Schedule-related datetime fields for PATCH; only non-``None`` fields are merged."""

    createddate: EamDateTimeBlock | None = None
    reported: EamDateTimeBlock | None = None
    targetdate: EamDateTimeBlock | None = None
    schedend: EamDateTimeBlock | None = None
    requested_start: EamDateTimeBlock | None = None
    requested_end: EamDateTimeBlock | None = None

    def to_patch_overrides(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for attr, json_key in _EAM_SCHEDULE_DATE_KEYS:
            block = getattr(self, attr)
            if block is not None:
                out[json_key] = block.to_eam_dict()
        return out
