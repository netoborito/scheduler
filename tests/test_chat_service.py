"""Tests for the chat service tool dispatch."""

import json
from unittest.mock import patch

import pytest

from app.services.chat_service import dispatch_tool


@patch("app.services.chat_service.load_gains")
def test_get_gains(mock_load):
    mock_load.return_value = {"priority": 1, "safety": 1}
    result = json.loads(dispatch_tool("get_gains", {}))
    assert "gains" in result
    assert "defaults" in result
    assert result["gains"]["priority"] == 1


@patch("app.services.chat_service.save_gains")
@patch("app.services.chat_service.validate_gains")
def test_update_gains(mock_validate, mock_save):
    result = json.loads(dispatch_tool("update_gains", {"gains": {"priority": 5}}))
    assert result["status"] == "ok"
    mock_validate.assert_called_once()
    mock_save.assert_called_once()


@patch("app.services.chat_service.load_hints")
def test_get_hints(mock_load):
    mock_load.return_value = {"42": ("monday", "NC-E/I", True)}
    result = json.loads(dispatch_tool("get_hints", {}))
    assert len(result["hints"]) == 1
    assert result["hints"][0]["work_order_id"] == "42"


@patch("app.services.chat_service.save_hints")
@patch("app.services.chat_service.load_hints", return_value={})
@patch("app.services.chat_service.validate_hint")
@patch("app.services.chat_service._fetch_backlog_map", return_value={
    "1": {"id": "1", "trade": "NC-E/I", "description": "Test", "priority": 1, "type": "CM", "duration_hours": 2},
})
def test_update_hints(mock_backlog, mock_validate, mock_load, mock_save):
    args = {"hints": [{"work_order_id": "1", "day": "monday", "trade": "NC-E/I", "scheduled": True}]}
    result = json.loads(dispatch_tool("update_hints", args))
    assert result["status"] == "ok"
    assert result["count"] == 1


@patch("app.services.chat_service.save_hints")
def test_clear_hints(mock_save):
    result = json.loads(dispatch_tool("clear_hints", {}))
    assert result["status"] == "ok"
    mock_save.assert_called_once_with({})


@patch("app.services.chat_service.load_preferences")
def test_get_preferences(mock_load):
    mock_load.return_value = [{"match": {"trade": ".*"}, "set": {"trade": "X"}}]
    result = json.loads(dispatch_tool("get_preferences", {}))
    assert len(result["rules"]) == 1


@patch("app.services.chat_service.save_preferences")
@patch("app.services.chat_service.validate_rule")
def test_update_preferences(mock_validate, mock_save):
    args = {"rules": [{"match": {"trade": ".*"}, "set": {"trade": "X"}}]}
    result = json.loads(dispatch_tool("update_preferences", args))
    assert result["status"] == "ok"
    assert result["count"] == 1


def test_unknown_tool():
    result = json.loads(dispatch_tool("no_such_tool", {}))
    assert "error" in result


def test_update_gains_validation_error():
    with pytest.raises(ValueError):
        dispatch_tool("update_gains", {"gains": {"bogus_key": 1}})
