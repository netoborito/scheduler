"""Sweep load_balance and schedule_bonus gains to find optimal defaults."""

import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.domain import WorkOrder
from app.models.shift import Shift
from app.services.optimizer import DEFAULT_OBJECTIVE_GAINS, DAYS, ScheduleOptimizer


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

WEEKDAYS = dict(
    monday=True, tuesday=True, wednesday=True,
    thursday=True, friday=True, saturday=False, sunday=False,
)

SHIFTS = [
    Shift(trade="NC-E/I", shift_duration_hours=8, technicians_per_crew=6, **WEEKDAYS),
    Shift(trade="Mechanical", shift_duration_hours=8, technicians_per_crew=6, **WEEKDAYS),
    Shift(trade="Electrical", shift_duration_hours=8, technicians_per_crew=4, **WEEKDAYS),
]

START = date(2026, 4, 6)

WORK_ORDERS = [
    WorkOrder(id=1,  description="WO-1",  duration_hours=8, priority=1, schedule_date=START, trade="NC-E/I"),
    WorkOrder(id=2,  description="WO-2",  duration_hours=4, priority=2, schedule_date=START, trade="NC-E/I"),
    WorkOrder(id=3,  description="WO-3",  duration_hours=6, priority=3, schedule_date=START, trade="NC-E/I"),
    WorkOrder(id=4,  description="WO-4",  duration_hours=2, priority=1, schedule_date=START, trade="NC-E/I"),
    WorkOrder(id=5,  description="WO-5",  duration_hours=8, priority=2, schedule_date=START, trade="NC-E/I"),
    WorkOrder(id=6,  description="WO-6",  duration_hours=3, priority=4, schedule_date=START, trade="NC-E/I"),
    WorkOrder(id=7,  description="WO-7",  duration_hours=8, priority=1, schedule_date=START, trade="Mechanical"),
    WorkOrder(id=8,  description="WO-8",  duration_hours=6, priority=2, schedule_date=START, trade="Mechanical"),
    WorkOrder(id=9,  description="WO-9",  duration_hours=4, priority=3, schedule_date=START, trade="Mechanical"),
    WorkOrder(id=10, description="WO-10", duration_hours=8, priority=1, schedule_date=START, trade="Mechanical"),
    WorkOrder(id=11, description="WO-11", duration_hours=2, priority=5, schedule_date=START, trade="Mechanical"),
    WorkOrder(id=12, description="WO-12", duration_hours=6, priority=2, schedule_date=START, trade="Electrical"),
    WorkOrder(id=13, description="WO-13", duration_hours=4, priority=1, schedule_date=START, trade="Electrical"),
    WorkOrder(id=14, description="WO-14", duration_hours=8, priority=3, schedule_date=START, trade="Electrical"),
]


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_once(lb_gain: float, sb_gain: float) -> dict:
    gains = {**DEFAULT_OBJECTIVE_GAINS, "load_balance": lb_gain, "schedule_bonus": sb_gain}
    with patch("app.services.optimizer.load_shifts", return_value=SHIFTS):
        opt = ScheduleOptimizer(
            work_orders=list(WORK_ORDERS), start_date=START, objective_gains=gains
        )
        schedule = opt.optimize()

    assigned = len(schedule.assignments)

    wo_by_id = {wo.id: wo for wo in WORK_ORDERS}
    load: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for a in schedule.assignments:
        wo = wo_by_id.get(a.work_order_id)
        if wo:
            day_name = DAYS[a.day_offset]
            load[a.resource_id][day_name] += wo.duration_hours

    shift_stats = {}
    for trade in [s.trade for s in SHIFTS]:
        daily = [load[trade].get(d, 0) for d in DAYS[:5]]
        shift_stats[trade] = {
            "daily": daily,
            "max": max(daily),
            "stdev": round(statistics.stdev(daily), 2) if len(daily) > 1 else 0,
        }

    return {"assigned": assigned, "shifts": shift_stats}


def main():
    print(f"Current defaults: {DEFAULT_OBJECTIVE_GAINS}\n")

    lb_values = [0.5, 1, 2, 5, 10, 20]
    sb_values = [5, 10, 50]

    for sb in sb_values:
        print(f"\n=== schedule_bonus={sb} ===")
        print(f"{'LB':>6}  {'Asgn':>4}  ", end="")
        for s in SHIFTS:
            print(f"  {s.trade:>12} max  stdev  daily", end="")
        print()
        print("-" * 150)

        for lb in lb_values:
            result = run_once(lb, sb)
            print(f"{lb:>6}  {result['assigned']:>4}  ", end="")
            for s in SHIFTS:
                st = result["shifts"][s.trade]
                daily_str = " ".join(f"{h:4.0f}" for h in st["daily"])
                print(f"  {st['max']:>12.0f}  {st['stdev']:>5.2f}  [{daily_str}]", end="")
            print()


if __name__ == "__main__":
    main()
