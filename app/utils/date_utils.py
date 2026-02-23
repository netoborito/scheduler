"""Date utility functions for scheduling."""
from datetime import date, timedelta
from typing import Optional


def get_next_monday(base_date: Optional[date] = None) -> date:
    """Get the next Monday from the given date (or today if not provided).
    
    If the given date is already a Monday, returns that date.
    Otherwise, returns the next Monday.
    
    Args:
        base_date: Base date to calculate from. If None, uses today.
    
    Returns:
        The next Monday date (or today if today is Monday).
    """
    if base_date is None:
        base_date = date.today()
    
    # Monday is weekday 0 in Python's datetime
    days_until_monday = (7 - base_date.weekday()) % 7
    # If today is Monday, days_until_monday will be 0, which is correct
    # If today is Tuesday-Sunday, it will be 1-6, giving us next Monday
    
    if days_until_monday == 0:
        # Today is Monday, return today
        return base_date
    else:
        # Return next Monday
        return base_date + timedelta(days=days_until_monday)
