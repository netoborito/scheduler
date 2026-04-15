"""Tests for the agent hints service."""

import json
from pathlib import Path

import pytest

from app.services.hints_service import load_hints, save_hints, validate_hint


def test_load_hints_returns_empty_when_no_file(tmp_path):
    assert load_hints(tmp_path / "missing.json") == {}


def test_save_and_load_round_trips(tmp_path):
    path = tmp_path / "hints.json"
    hints = {"100": ("monday", "NC-E/I", True), "200": ("friday", "Mechanical", False)}
    save_hints(hints, path)
    assert load_hints(path) == hints


def test_validate_hint_rejects_bad_day():
    with pytest.raises(ValueError, match="Invalid day"):
        validate_hint("funday", "NC-E/I", True)


def test_validate_hint_rejects_empty_trade():
    with pytest.raises(ValueError, match="non-empty string"):
        validate_hint("monday", "  ", True)


def test_validate_hint_rejects_non_bool_scheduled():
    with pytest.raises(ValueError, match="bool"):
        validate_hint("monday", "NC-E/I", 1)  # type: ignore[arg-type]
