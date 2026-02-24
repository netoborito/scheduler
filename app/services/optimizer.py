from __future__ import annotations

from typing import List, Optional, Set
from datetime import date, timedelta
from app.services.shift_service import load_shifts
from collections import defaultdict
from ortools.sat.python import cp_model

from app.models.domain import WorkOrder, Assignment, Schedule


def optimize_schedule(
        work_orders: List[WorkOrder], start_date: Optional[date] = None) -> Schedule:

    # Create the model
    model = cp_model.CpModel()

    # Define the horizon
    horizon_days = 7  # Fixed 7-day horizon

    # Get all shifts
    shifts = load_shifts()

    if not shifts:
        return Schedule(assignments=[], horizon_days=horizon_days)

    # Decision variables: x[wo.id][resource][day] = 1 if assigned
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

    objective_gains = {
        "age": .1,
        "priority": 1,
        "safety": 1,
        "type": 1,
    }

    for crew in shifts:

        crew_wo = [wo for wo in work_orders if wo.trade == crew.trade]

        for day in days:

            if crew.is_active_on_day(day):

                shift_wo = []

                for wo in crew_wo:
                    if wo.fixed and wo.schedule_date == start_date+timedelta(days=days.index(day)):
                        x[wo.id, crew.trade, day] = model.NewConstant(1)
                    else:
                        x[wo.id, crew.trade, day] = model.NewBoolVar(
                            f"x_{wo.id}_{crew.trade}_{day}"
                        )

                    shift_wo.append(x[wo.id, crew.trade, day]
                                    * wo.duration_hours)

                # Add constraint: total work order duration per day per crew <= technicians_per_crew * shift_duration_hours
                model.Add(
                    sum(
                        shift_wo
                    )
                    <= crew.technicians_per_crew * crew.shift_duration_hours
                )

    # Work order scheduled only once: sum of all x for this wo.id <= 1
    for wo in work_orders:
        wo_vars = [var for (wo_id, trade, day),
                   var in x.items() if wo_id == wo.id]
        model.Add(sum(wo_vars) <= 1)

    # Objective: prioritize across several parameters based on gains for fine-tuning
    objective_terms = []

    wo_by_id = {wo.id: wo for wo in work_orders}
    for (wo_id, trade, day), var in x.items():

        wo = wo_by_id.get(wo_id)

        type_as_int = 1 if wo.type == "Preventive maintenance" else 0
        safety_as_int = 1 if wo.safety else 0

        objective_terms.append(var * wo.age_days * objective_gains["age"])
        objective_terms.append(var * (5-wo.priority) *
                               objective_gains["priority"])
        objective_terms.append(var * safety_as_int * objective_gains["safety"])
        objective_terms.append(var * type_as_int * objective_gains["type"])

    model.Maximize(sum(objective_terms))

    # Solve the model
    solver = cp_model.CpSolver()
    solver_status = solver.Solve(model)

    # Create the schedule
    assignments = []

    if solver_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for (wo_id, trade, day), var in x.items():
            if solver.Value(var) > 0.5:
                assignments.append(
                    Assignment(
                        work_order_id=wo_id,
                        day_offset=days.index(day),
                        resource_id=trade,
                    )
                )

    return Schedule(assignments=assignments, horizon_days=horizon_days, start_date=start_date,)
