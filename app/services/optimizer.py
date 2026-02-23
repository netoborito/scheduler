from __future__ import annotations

from typing import List, Optional, Set
from datetime import date
from app.services.shift_service import load_shifts
from ortools.sat.python import cp_model

from app.models.domain import WorkOrder, Assignment, Schedule
from collections import defaultdict

HOURS_PER_DAY = 8.0


def optimize_schedule(
    work_orders: List[WorkOrder], start_date: Optional[date] = None
) -> Schedule:
    """Optimize schedule for a fixed 7-day horizon starting from start_date."""
    horizon_days = 7  # Fixed 7-day horizon
    """Optimize schedule using work order trades as resources."""
    model = cp_model.CpModel()

    # Get all shifts
    shifts = load_shifts()

    if not shifts:
        return Schedule(assignments=[], horizon_days=horizon_days)

    # Decision variables: x[wo.id][duration][resource][day] = 1 if assigned
    # Only create variables for days that the crew is active
    x = {}
    days = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]

    for crew in shifts:

        crew_wo = [wo for wo in work_orders if wo.trade == crew.trade]

        for day in days:
            if crew.is_active_on_day(day):
                for wo in crew_wo:
                    x[wo.id, wo.duration_hours, crew.trade, day] = model.NewBoolVar(
                        f"x_{wo.id}_{wo.duration_hours}_{crew.trade}_{day}"
                    )
                model.Add(
                    sum(
                        x[wo.id, wo.duration_hours, crew.trade, day] * wo.duration_hours
                        for wo in crew_wo
                    )
                    <= crew.technicians_per_crew * crew.shift_duration_hours
                )

    # unique assignment per work order
    possible_wo_assignments = defaultdict(list)

    for (wo_id, duration, trade, day), var in x.items():
        possible_wo_assignments[wo_id].append(var)

    for wo_id, vars in possible_wo_assignments.items():
        model.Add(sum(vars) <= 1)

    # Objective: prioritize higher priority work orders earlier
    objective_terms = []

    for (wo_id, duration, trade, day), var in x.items():
    for wo in work_orders:
        r = wo.trade
        for d in range(horizon_days):
            # Higher priority (larger number) and earlier days are preferred
            weight = wo.priority * (horizon_days - d)
            objective_terms.append(weight * x[(wo.id, r, d)])


    model.minimize(-sum(objective_terms))

    solver = cp_model.CpSolver()
    solver_status = solver.Solve(model)

    assignments: List[Assignment] = []
    if solver_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for wo in work_orders:
            r = wo.trade
            for d in range(horizon_days):
                if solver.Value(x[(wo.id, r, d)]) > 0.5:
                    assignments.append(
                        Assignment(
                            work_order_id=wo.id,
                            day_offset=d,
                            resource_id=r,
                        )
                    )

    if start_date is None:
        from app.utils.date_utils import get_next_monday

        start_date = get_next_monday()

    return Schedule(
        assignments=assignments, horizon_days=horizon_days, start_date=start_date
    )
