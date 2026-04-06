"""Tests for date utilities."""

from datetime import date, timedelta

from app.utils.date_utils import get_next_monday


def test_next_monday_from_monday_moves_ahead_one_week():
    monday = date(2026, 4, 6)
    assert monday.weekday() == 0
    assert get_next_monday(monday) == monday + timedelta(days=7)


def test_next_monday_from_tuesday():
    tuesday = date(2026, 4, 7)
    assert tuesday.weekday() == 1
    assert get_next_monday(tuesday) == date(2026, 4, 13)


def test_next_monday_from_sunday():
    sunday = date(2026, 4, 5)
    assert sunday.weekday() == 6
    assert get_next_monday(sunday) == date(2026, 4, 6)
