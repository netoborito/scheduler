"""Tests for the gains service."""

import json
from pathlib import Path

import pytest

from app.services.gains_service import load_gains, save_gains, validate_gains
from app.services.optimizer import DEFAULT_OBJECTIVE_GAINS


def test_load_gains_returns_defaults_when_no_file(tmp_path):
    result = load_gains(tmp_path / "missing.json")
    assert result == DEFAULT_OBJECTIVE_GAINS


def test_save_and_load_round_trips(tmp_path):
    path = tmp_path / "gains.json"
    custom = {**DEFAULT_OBJECTIVE_GAINS, "load_balance": 5.0}
    save_gains(custom, path)
    assert load_gains(path) == custom


def test_load_gains_merges_partial_file(tmp_path):
    path = tmp_path / "gains.json"
    path.write_text(json.dumps({"load_balance": 7.0}))
    result = load_gains(path)
    assert result["load_balance"] == 7.0
    assert result["priority"] == DEFAULT_OBJECTIVE_GAINS["priority"]


def test_validate_gains_rejects_unknown_key():
    with pytest.raises(ValueError, match="Unknown gain key"):
        validate_gains({"bogus": 1.0})


def test_validate_gains_rejects_negative_value():
    with pytest.raises(ValueError, match="non-negative"):
        validate_gains({"load_balance": -1})


def test_validate_gains_rejects_bonus_lte_load_balance():
    with pytest.raises(ValueError, match="schedule_bonus.*must be greater"):
        validate_gains({"schedule_bonus": 1, "load_balance": 5})
