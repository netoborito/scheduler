"""Date utility functions for scheduling."""
from datetime import date, timedelta
from typing import Optional


def get_next_monday(base_date: Optional[date] = None) -> date:
    """Get the next Monday from the given date (or today if not provided).

    Args:
        base_date: Base date to calculate from. If None, uses today.

    Returns:
        The next Monday date
    """
    if base_date is None:
        base_date = date.today()

    # Monday is weekday 0 in Python's datetime
    days_until_monday = (7 - base_date.weekday()) % 7
    if days_until_monday == 0:
        return base_date + timedelta(days=7)
    else:
        return base_date + timedelta(days=days_until_monday)
