"""Tests for CloudBacklogClient."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import httpx
import pandas as pd
import pytest

from app.config import BacklogIntegrationSettings
from app.models.domain import Assignment, Schedule, WorkOrder
from app.services.cloud_backlog_client import (
    CloudBacklogClient,
    CloudBacklogError,
    _parse_eam_payload_to_dataframe,
)


def _settings() -> BacklogIntegrationSettings:
    return BacklogIntegrationSettings(
        rest_url="http://127.0.0.1:9",
        api_key="secret",
        http_timeout_seconds=5,
        tenant_id="T1",
        organization="Org",
        grid_id=100195,
        dataspy_id=42,
        backlog_endpoint="/grids",
        schedule_endpoint="/workorders",
    )


def _eam_payload() -> dict:
    """Minimal DATARECORD/DATAFIELD payload matching current parser."""
    return {
        "Result": {
            "ResultData": {
                "DATARECORD": [
                    {
                        "DATAFIELD": [
                            {"FIELDLABEL": "Work Order", "FIELDVALUE": "1001"},
                            {"FIELDLABEL": "Trade", "FIELDVALUE": "ELEC"},
                        ]
                    },
                    {
                        "DATAFIELD": [
                            {"FIELDLABEL": "Work Order", "FIELDVALUE": "1002"},
                            {"FIELDLABEL": "Trade", "FIELDVALUE": "MECH"},
                        ]
                    },
                ]
            }
        }
    }


def _mock_httpx_session(mock_client_cls, mock_response):
    session = MagicMock()
    session.request.return_value = mock_response
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    mock_client_cls.return_value = session
    return session


# ---------------------------------------------------------------------------
# fetch_backlog
# ---------------------------------------------------------------------------


@pytest.fixture()
def ok_response():
    r = MagicMock(spec=httpx.Response)
    r.is_success = True
    r.json.return_value = _eam_payload()
    return r


def test_fetch_backlog_returns_dataframe(ok_response, monkeypatch):
    with monkeypatch.context() as m:
        mock_cls = MagicMock()
        m.setattr("app.services.cloud_backlog_client.httpx.Client", mock_cls)
        session = _mock_httpx_session(mock_cls, ok_response)

        df = CloudBacklogClient(settings=_settings()).fetch_backlog()

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["Work Order", "Trade"]
    assert df.iloc[0].tolist() == ["1001", "ELEC"]
    assert df.iloc[1].tolist() == ["1002", "MECH"]

    mock_cls.assert_called_once_with(timeout=5)
    _, kwargs = session.request.call_args
    assert kwargs["headers"]["X-API-Key"] == "secret"
    body = kwargs["json"]
    assert body["GRID"]["GRID_ID"] == 100195
    assert body["DATASPY"]["DATASPY_ID"] == 42
    assert body["REQUEST_TYPE"] == "LIST.HEAD_DATA.STORED"


def test_fetch_backlog_raises_on_http_error(monkeypatch):
    r = MagicMock(spec=httpx.Response)
    r.is_success = False
    r.status_code = 400
    r.text = "bad request"

    with monkeypatch.context() as m:
        mock_cls = MagicMock()
        m.setattr("app.services.cloud_backlog_client.httpx.Client", mock_cls)
        _mock_httpx_session(mock_cls, r)

        with pytest.raises(CloudBacklogError, match="400") as exc_info:
            CloudBacklogClient(settings=_settings()).fetch_backlog()
        assert exc_info.value.response is r


def test_fetch_backlog_raises_on_invalid_json(monkeypatch):
    r = MagicMock(spec=httpx.Response)
    r.is_success = True
    r.json.side_effect = ValueError("not json")

    with monkeypatch.context() as m:
        mock_cls = MagicMock()
        m.setattr("app.services.cloud_backlog_client.httpx.Client", mock_cls)
        _mock_httpx_session(mock_cls, r)

        with pytest.raises(CloudBacklogError, match="JSON") as exc_info:
            CloudBacklogClient(settings=_settings()).fetch_backlog()
        assert exc_info.value.response is r


def test_fetch_backlog_wraps_request_error(monkeypatch):
    with monkeypatch.context() as m:
        mock_cls = MagicMock()
        m.setattr("app.services.cloud_backlog_client.httpx.Client", mock_cls)
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        session.request.side_effect = httpx.ConnectError("simulated", request=MagicMock())
        mock_cls.return_value = session

        with pytest.raises(CloudBacklogError, match="EAM request failed"):
            CloudBacklogClient(settings=_settings()).fetch_backlog()


def test_parse_drops_duplicate_columns():
    payload = {
        "Result": {
            "ResultData": {
                "DATARECORD": [
                    {
                        "DATAFIELD": [
                            {"FIELDLABEL": "Work Order", "FIELDVALUE": "1001"},
                            {"FIELDLABEL": "Status", "FIELDVALUE": ""},
                            {"FIELDLABEL": "Status", "FIELDVALUE": "Open - Ready to Schedule"},
                        ]
                    },
                ]
            }
        }
    }
    df = _parse_eam_payload_to_dataframe(payload)

    assert list(df.columns) == ["Work Order", "Status"]
    assert df.iloc[0]["Status"] == "Open - Ready to Schedule"


# ---------------------------------------------------------------------------
# patch_eam_schedule_data
# ---------------------------------------------------------------------------


def test_patch_sends_correct_request(monkeypatch):
    r = MagicMock(spec=httpx.Response)
    r.is_success = True
    r.json.return_value = {"ok": True}

    with monkeypatch.context() as m:
        mock_cls = MagicMock()
        m.setattr("app.services.cloud_backlog_client.httpx.Client", mock_cls)
        session = _mock_httpx_session(mock_cls, r)

        start = date(2026, 1, 5)
        wo = WorkOrder(
            id=123, description="t", duration_hours=1.0,
            priority=1, schedule_date=start, trade="ELEC",
        )
        schedule = Schedule(
            assignments=[Assignment(work_order_id="123", day_offset=0, resource_id="r")],
            horizon_days=7,
            start_date=start,
        )

        result = CloudBacklogClient(settings=_settings()).patch_eam_schedule_data(wo, schedule)

    assert result == {"ok": True}

    args, kwargs = session.request.call_args
    assert args[0] == "PATCH"
    assert args[1] == "http://127.0.0.1:9/workorders/123%23AZP%20MOORESBORO"
    assert kwargs["headers"]["X-API-Key"] == "secret"

    body = kwargs["json"]
    assert body["WORKORDERID"]["JOBNUM"] == 123
    expected_year_ux = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    assert body["STARTDATE"]["YEAR"] == expected_year_ux
    assert body["STARTDATE"]["MONTH"] == 1
    assert body["STARTDATE"]["DAY"] == 5
    assert body["STARTDATE"]["HOUR"] == 7
    assert body["STARTDATE"]["TIMEZONE"] == "-0500"
    assert body["STARTDATE"]["qualifier"] == "OTHER"
