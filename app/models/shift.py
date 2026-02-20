"""Shift data models."""
from dataclasses import dataclass, asdict
from typing import Dict


@dataclass
class Shift:
    """Represents a work shift configuration."""

    trade: str  # Trade/resource type (e.g., "NC-E/I")
    shift_duration_hours: int  # Duration of shift in hours
    monday: bool = False
    tuesday: bool = False
    wednesday: bool = False
    thursday: bool = False
    friday: bool = False
    saturday: bool = False
    sunday: bool = False
    technicians_per_crew: int = 1  # Number of technicians in this crew

    def to_dict(self) -> Dict:
        """Convert shift to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "Shift":
        """Create Shift from dictionary."""
        return cls(**data)

    def get_active_days(self) -> list[str]:
        """Get list of active day names."""
        days = []
        if self.monday:
            days.append("monday")
        if self.tuesday:
            days.append("tuesday")
        if self.wednesday:
            days.append("wednesday")
        if self.thursday:
            days.append("thursday")
        if self.friday:
            days.append("friday")
        if self.saturday:
            days.append("saturday")
        if self.sunday:
            days.append("sunday")
        return days

    def is_active_on_day(self, day_name: str) -> bool:
        """Check if shift is active on a specific day."""
        day_map = {
            "monday": self.monday,
            "tuesday": self.tuesday,
            "wednesday": self.wednesday,
            "thursday": self.thursday,
            "friday": self.friday,
            "saturday": self.saturday,
            "sunday": self.sunday,
        }
        return day_map.get(day_name.lower(), False)
