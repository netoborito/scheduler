"""Tests for EAM schedule PATCH template merge and ``patch_eam_schedule_data``."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.config import BacklogIntegrationSettings, get_backlog_integration_settings
from app.models.eam_schedule import EamDateTimeBlock, EamWorkOrderScheduleData
from app.services.cloud_backlog_client import CloudBacklogClient, CloudBacklogError
from app.services.work_order_patch_payload import (
    build_eam_patch_body,
    build_work_order_patch_body,
    deep_merge,
    eam_date_block,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TEMPLATE_MIN = FIXTURES / "eam_patch_template_min.json"
GOLDEN_MERGED = FIXTURES / "eam_patch_golden_merged.json"


def _dt(**kwargs) -> EamDateTimeBlock:
    defaults = {
        "year": 1704067200000,
        "month": 12,
        "day": 10,
        "hour": 15,
        "minute": 25,
        "second": 0,
        "subsecond": 0,
        "timezone": "+0530",
        "qualifier": "OTHER",
    }
    defaults.update(kwargs)
    return EamDateTimeBlock(**defaults)


def test_eam_date_block_matches_confirmed_api_keys():
    d = eam_date_block(
        1704067200000,
        12,
        9,
        15,
        25,
        48,
        477,
        "+0530",
        "OTHER",
    )
    assert set(d) == {
        "YEAR",
        "MONTH",
        "DAY",
        "HOUR",
        "MINUTE",
        "SECOND",
        "SUBSECOND",
        "TIMEZONE",
        "qualifier",
    }
    assert d["SUBSECOND"] == 477
    assert d["qualifier"] == "OTHER"


def test_build_work_order_patch_body_requires_template_source():
    with pytest.raises(ValueError, match="template"):
        build_work_order_patch_body(schedule=EamWorkOrderScheduleData())


def test_build_work_order_patch_body_golden_merged_json():
    schedule = EamWorkOrderScheduleData(
        createddate=_dt(day=9, second=48, subsecond=477),
    )
    body = build_work_order_patch_body(
        schedule=schedule,
        template_path=TEMPLATE_MIN,
    )
    expected = json.loads(GOLDEN_MERGED.read_text(encoding="utf-8"))
    assert body == expected


def test_build_work_order_patch_body_in_memory_template():
    template = {
        "STATUS": {"STATUSCODE": "R", "DESCRIPTION": "Released"},
        "FIXED": "V",
    }
    schedule = EamWorkOrderScheduleData(
        reported=_dt(
            year=1,
            month=2,
            day=3,
            hour=4,
            minute=5,
            second=6,
            subsecond=7,
            timezone="+0000",
            qualifier="OTHER",
        ),
    )
    body = build_work_order_patch_body(template=template, schedule=schedule)
    assert body["STATUS"]["STATUSCODE"] == "R"
    assert body["REPORTED"]["DAY"] == 3
    assert body["FIXED"] == "V"


def test_deep_merge_nested_dicts():
    base = {"a": 1, "STATUS": {"STATUSCODE": "R", "DESCRIPTION": "Released"}}
    patch = {"STATUS": {"STATUSCODE": "C"}}
    assert deep_merge(base, patch) == {
        "a": 1,
        "STATUS": {"STATUSCODE": "C", "DESCRIPTION": "Released"},
    }


def test_eam_work_order_schedule_data_to_patch_overrides_only_set_fields():
    schedule = EamWorkOrderScheduleData(
        createddate=_dt(day=9, second=48, subsecond=477),
        targetdate=_dt(hour=0, minute=0),
    )
    o = schedule.to_patch_overrides()
    assert set(o) == {"CREATEDDATE", "TARGETDATE"}
    assert o["CREATEDDATE"]["DAY"] == 9
    assert o["TARGETDATE"]["HOUR"] == 0


def test_build_eam_patch_body_replaces_dates_from_schedule():
    schedule = EamWorkOrderScheduleData(
        createddate=_dt(year=99, month=5, day=6),
    )
    body = build_eam_patch_body(TEMPLATE_MIN, schedule)
    assert body["CREATEDDATE"]["YEAR"] == 99
    assert body["CREATEDDATE"]["MONTH"] == 5
    assert body["CREATEDDATE"]["DAY"] == 6
    assert body["TARGETDATE"]["YEAR"] == 2
    assert body["STATUS"]["STATUSCODE"] == "R"


def test_build_eam_patch_body_includes_fixed_from_template_file():
    schedule = EamWorkOrderScheduleData()
    body = build_eam_patch_body(TEMPLATE_MIN, schedule)
    assert body["FIXED"] == "V"
    assert body["DEPEND"] == "false"


def _client_settings(**kwargs) -> BacklogIntegrationSettings:
    base = dict(
        rest_url="http://127.0.0.1:9/backlog",
        api_key="secret",
        http_timeout_seconds=5,
        tenant_id="T1",
        organization="Org",
        grid_id=1,
        dataspy_id=1,
        work_order_api_base_url="http://127.0.0.1:9/api",
        eam_patch_template_path="",
    )
    base.update(kwargs)
    return BacklogIntegrationSettings(**base)


@patch("app.services.cloud_backlog_client.httpx.Client")
def test_patch_eam_schedule_data_sends_merged_json(mock_client_cls):
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.is_success = True
    mock_response.json.return_value = {"ok": True}

    mock_session = MagicMock()
    mock_session.request.return_value = mock_response
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_client_cls.return_value = mock_session

    schedule = EamWorkOrderScheduleData(createddate=_dt(day=99))
    out = CloudBacklogClient(
        settings=_client_settings(eam_patch_template_path=str(TEMPLATE_MIN))
    ).patch_eam_schedule_data(1452479, schedule)

    assert out == {"ok": True}
    mock_session.request.assert_called_once()
    args, kwargs = mock_session.request.call_args
    assert args[0] == "PATCH"
    assert args[1] == "http://127.0.0.1:9/api/workorders/1452479"
    sent = kwargs["json"]
    assert sent["CREATEDDATE"]["DAY"] == 99
    assert sent["FIXED"] == "V"


@patch("app.services.cloud_backlog_client.httpx.Client")
def test_patch_eam_schedule_data_resolves_template_from_settings(mock_client_cls, monkeypatch):
    monkeypatch.setenv("EAM_PATCH_TEMPLATE_PATH", str(TEMPLATE_MIN))
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.is_success = True
    mock_response.json.return_value = {"ok": True}

    mock_session = MagicMock()
    mock_session.request.return_value = mock_response
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_client_cls.return_value = mock_session

    schedule = EamWorkOrderScheduleData(createddate=_dt(day=5))
    settings = get_backlog_integration_settings()
    assert settings.eam_patch_template_path == str(TEMPLATE_MIN)

    CloudBacklogClient(settings=settings).patch_eam_schedule_data(9, schedule)

    _, kwargs = mock_session.request.call_args
    assert kwargs["json"]["CREATEDDATE"]["DAY"] == 5


def test_patch_eam_schedule_data_wraps_missing_template():
    schedule = EamWorkOrderScheduleData()
    try:
        CloudBacklogClient(
            settings=_client_settings(
                eam_patch_template_path=str(FIXTURES / "nonexistent.json")
            )
        ).patch_eam_schedule_data(1, schedule)
    except CloudBacklogError as e:
        assert "not found" in str(e).lower()
    else:
        raise AssertionError("expected CloudBacklogError")


def test_patch_eam_schedule_data_requires_template_when_unconfigured():
    schedule = EamWorkOrderScheduleData()
    with pytest.raises(CloudBacklogError, match="EAM_PATCH_TEMPLATE_PATH"):
        CloudBacklogClient(settings=_client_settings()).patch_eam_schedule_data(
            1,
            schedule,
        )
