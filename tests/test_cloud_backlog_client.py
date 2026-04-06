"""Tests for CloudBacklogClient."""

from dataclasses import replace
from unittest.mock import MagicMock, patch

import httpx
import pandas as pd

from datetime import date

from app.config import BacklogIntegrationSettings
from app.models.domain import Assignment, Schedule, WorkOrder
from app.services import cloud_backlog_client as cbc
from app.services.cloud_backlog_client import CloudBacklogClient, CloudBacklogError


def _sample_settings() -> BacklogIntegrationSettings:
    return BacklogIntegrationSettings(
        rest_url="http://127.0.0.1:9/backlog",
        api_key="secret",
        http_timeout_seconds=5,
        tenant_id="T1",
        organization="Org",
        grid_id=100195,
        dataspy_id=42,
        work_order_api_base_url="http://127.0.0.1:9/api",
        eam_patch_template_path="",
    )


def _eam_payload_two_rows() -> dict:
    return {
        "Result": {
            "ResultData": {
                "GRID": {
                    "DATA": {
                        "ROW": [
                            {"id": 1, "D": [{"value": "a", "n": 0}, {"value": "b", "n": 1}]},
                            {"id": 2, "D": [{"value": "c", "n": 0}]},
                        ]
                    }
                }
            }
        }
    }


@patch("app.services.cloud_backlog_client.httpx.Client")
def test_fetch_backlog_returns_dataframe(mock_client_cls, monkeypatch):
    monkeypatch.setattr(cbc, "BACKLOG_CSV_COLUMNS", ("column_0", "column_1"))
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.is_success = True
    mock_response.json.return_value = _eam_payload_two_rows()

    mock_session = MagicMock()
    mock_session.request.return_value = mock_response
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_client_cls.return_value = mock_session

    client = CloudBacklogClient(settings=_sample_settings())
    result = client.fetch_backlog()

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["column_0", "column_1"]
    assert result.iloc[0].tolist() == ["a", "b"]
    assert result.iloc[1].tolist() == ["c", ""]
    mock_client_cls.assert_called_once_with(timeout=5)
    mock_session.request.assert_called_once()
    args, kwargs = mock_session.request.call_args
    assert args[0] == "POST"
    assert args[1] == "http://127.0.0.1:9/backlog"
    assert kwargs["headers"]["X-API-Key"] == "secret"
    posted = kwargs["json"]
    assert posted["GRID"]["GRID_ID"] == 100195
    assert posted["DATASPY"]["DATASPY_ID"] == 42
    assert posted["REQUEST_TYPE"] == "LIST.DATA_ONLY.STORED"


@patch("app.services.cloud_backlog_client.httpx.Client")
def test_fetch_backlog_non_eam_json_raises(mock_client_cls, monkeypatch):
    monkeypatch.setattr(cbc, "BACKLOG_CSV_COLUMNS", ("column_0", "column_1"))
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.is_success = True
    mock_response.json.return_value = {"rows": [{"id": 1}]}

    mock_session = MagicMock()
    mock_session.request.return_value = mock_response
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_client_cls.return_value = mock_session

    try:
        CloudBacklogClient(settings=_sample_settings()).fetch_backlog()
    except CloudBacklogError as e:
        assert "eam grid rows" in str(e).lower()
        assert e.response is mock_response
    else:
        raise AssertionError("expected CloudBacklogError")


@patch("app.services.cloud_backlog_client.httpx.Client")
def test_fetch_backlog_writes_debug_csv_when_env_set(
    mock_client_cls, tmp_path, monkeypatch
):
    monkeypatch.setattr(cbc, "BACKLOG_CSV_COLUMNS", ("column_0", "column_1"))
    out = tmp_path / "debug.csv"
    monkeypatch.setenv("BACKLOG_DEBUG_CSV", str(out))
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.is_success = True
    mock_response.json.return_value = _eam_payload_two_rows()

    mock_session = MagicMock()
    mock_session.request.return_value = mock_response
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_client_cls.return_value = mock_session

    CloudBacklogClient(settings=_sample_settings()).fetch_backlog()

    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "column_0" in text and "column_1" in text


@patch("app.services.cloud_backlog_client.httpx.Client")
def test_fetch_backlog_skips_csv_when_debug_unset(
    mock_client_cls, tmp_path, monkeypatch
):
    monkeypatch.setattr(cbc, "BACKLOG_CSV_COLUMNS", ("column_0", "column_1"))
    monkeypatch.delenv("BACKLOG_DEBUG_CSV", raising=False)
    would_be = tmp_path / "should_not_exist.csv"

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.is_success = True
    mock_response.json.return_value = _eam_payload_two_rows()

    mock_session = MagicMock()
    mock_session.request.return_value = mock_response
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_client_cls.return_value = mock_session

    CloudBacklogClient(settings=_sample_settings()).fetch_backlog()

    assert not would_be.exists()


@patch("app.services.cloud_backlog_client.httpx.Client")
def test_fetch_backlog_raises_cloud_backlog_error_on_http_error(mock_client_cls):
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.is_success = False
    mock_response.status_code = 400
    mock_response.text = "bad request"

    mock_session = MagicMock()
    mock_session.request.return_value = mock_response
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_client_cls.return_value = mock_session

    client = CloudBacklogClient(settings=_sample_settings())
    try:
        client.fetch_backlog()
    except CloudBacklogError as e:
        assert e.response is mock_response
        assert "400" in str(e)
    else:
        raise AssertionError("expected CloudBacklogError")


@patch("app.services.cloud_backlog_client.httpx.Client")
def test_fetch_backlog_raises_on_invalid_json(mock_client_cls):
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.is_success = True
    mock_response.json.side_effect = ValueError("not json")

    mock_session = MagicMock()
    mock_session.request.return_value = mock_response
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_client_cls.return_value = mock_session

    try:
        CloudBacklogClient(settings=_sample_settings()).fetch_backlog()
    except CloudBacklogError as e:
        assert "JSON" in str(e)
        assert e.response is mock_response
    else:
        raise AssertionError("expected CloudBacklogError")


@patch("app.services.cloud_backlog_client.httpx.Client")
def test_fetch_backlog_wraps_request_error(mock_client_cls):
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.request.side_effect = httpx.ConnectError("simulated", request=MagicMock())
    mock_client_cls.return_value = mock_session

    try:
        CloudBacklogClient(settings=_sample_settings()).fetch_backlog()
    except CloudBacklogError as e:
        assert "simulated" in str(e).lower() or "request failed" in str(e).lower()
    else:
        raise AssertionError("expected CloudBacklogError")


@patch("app.services.cloud_backlog_client.httpx.Client")
def test_patch_eam_schedule_data_sends_patch_to_workorders_url(mock_client_cls):
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.is_success = True
    mock_response.json.return_value = {"ok": True}

    mock_session = MagicMock()
    mock_session.request.return_value = mock_response
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_client_cls.return_value = mock_session

    start = date(2026, 1, 5)
    wo = WorkOrder(
        id=123,
        description="t",
        duration_hours=1.0,
        priority=1,
        schedule_date=start,
        trade="ELEC",
    )
    schedule = Schedule(
        assignments=[
            Assignment(work_order_id="123", day_offset=0, resource_id="r"),
        ],
        horizon_days=7,
        start_date=start,
    )
    data, _response = CloudBacklogClient(
        settings=_sample_settings()
    ).patch_eam_schedule_data(wo, schedule)

    assert data == {"ok": True}
    mock_session.request.assert_called_once()
    args, kwargs = mock_session.request.call_args
    assert args[0] == "PATCH"
    assert args[1] == "http://127.0.0.1:9/api/workorders/123"
    assert kwargs["headers"]["X-API-Key"] == "secret"
    body = kwargs["json"]
    assert body["WORKORDERID"]["JOBNUM"] == 123
    assert body["STARTDATE"]["year"] == 2026


def test_patch_eam_schedule_data_raises_when_base_url_missing():
    s = replace(_sample_settings(), work_order_api_base_url="")
    start = date(2026, 1, 5)
    wo = WorkOrder(
        id=1,
        description="t",
        duration_hours=1.0,
        priority=1,
        schedule_date=start,
        trade="ELEC",
    )
    schedule = Schedule(
        assignments=[Assignment(work_order_id="1", day_offset=0, resource_id="r")],
        horizon_days=7,
        start_date=start,
    )
    try:
        CloudBacklogClient(settings=s).patch_eam_schedule_data(wo, schedule)
    except CloudBacklogError as e:
        assert "WORK_ORDER_API_BASE_URL" in str(e)
    else:
        raise AssertionError("expected CloudBacklogError")
