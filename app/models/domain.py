from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Dict, Optional


@dataclass
class WorkOrder:
    id: str
    description: str
    duration_hours: int  # Integer hours only, no fractions
    priority: int
    due_date: Optional[date]
    trade: str  # Required trade/resource type for this work order
    type: str = ""  # Work order type (e.g. "Corrective")
    safety: bool = False  # Safety flag from backlog
    age_days: int = 0  # Age of work order in days


@dataclass
class Assignment:
    work_order_id: str
    day_offset: int
    resource_id: str


@dataclass
class Schedule:
    assignments: List[Assignment]
    horizon_days: int
    start_date: date  # Schedule start date (next Monday)

    def to_api_payload(self) -> Dict:
        return {
            "horizon_days": self.horizon_days,
            "start_date": self.start_date.isoformat(),
            "assignments": [
                {
                    "work_order_id": a.work_order_id,
                    "day_offset": a.day_offset,
                    "resource_id": a.resource_id,
                }
                for a in self.assignments
            ],
        }

    def to_calendar_events(
        self,
        start_date: date,
        resource_hours_per_day: float = 8.0,
    ) -> List[Dict]:
        events: List[Dict] = []
        # Simple mapping: consume hours in order in a single daily block per WO
        for assignment in self.assignments:
            event_date = start_date + timedelta(days=assignment.day_offset)
            events.append(
                {
                    "title": assignment.work_order_id,
                    "resourceId": assignment.resource_id,
                    "start": event_date.isoformat(),
                    "end": event_date.isoformat(),
                }
            )
        return events
