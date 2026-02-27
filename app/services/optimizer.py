from __future__ import annotations

from typing import List, Optional, Set
from datetime import date, timedelta

from jinja2.environment import load_extensions
from app.services.shift_service import load_shifts
from collections import defaultdict
from ortools.sat.python import cp_model
import csv
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
    load_by_shift_and_day = defaultdict(list)

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
        "load_balance": 1,
    }

    for crew in shifts:

        crew_wo = [wo for wo in work_orders if wo.trade == crew.trade]

        for day in days:

            if crew.is_active_on_day(day):

                shift_wo = []
                shift_wo_fixed = []
                for wo in crew_wo:
                    # Decision variable: x[wo.id][resource][day] = 1 if assigned
                    x[wo.id, crew.trade, day] = model.NewBoolVar(
                        f"x_{wo.id}_{crew.trade}_{day}"
                    )

                    # Add to list of variables for each shift for balancing load in objective function 2
                    load_by_shift_and_day[crew.trade, day].append(
                        x[wo.id, crew.trade, day]*wo.duration_hours*wo.num_people)

                    # Add to list of wo for this shift in manhours for constraint 2
                    shift_wo.append(x[wo.id, crew.trade, day]
                                    * wo.duration_hours*wo.num_people)

                    # Constraint 1: If the work order is fixed, force it to be scheduled on the schedule date
                    if wo.fixed and wo.schedule_date == start_date+timedelta(days=days.index(day)):
                        model.Add(x[wo.id, crew.trade, day] == 1)
                        shift_wo_fixed.append(wo.duration_hours*wo.num_people)

                # Constraint 2: scheduled shift manhours <= shift capacity.
                # exception required if there are too many EHS work orders for a given shift.
                # that should be scheduled as is
                if sum(shift_wo_fixed) > crew.shift_duration_hours:
                    model.Add(
                        sum(shift_wo) <= sum(shift_wo_fixed)
                    )

                else:
                    model.Add(
                        sum(shift_wo) <= crew.technicians_per_crew *
                        crew.shift_duration_hours
                    )

    # Constraint 3: Work order scheduled only once: sum of all x for this wo.id <= 1
    for wo in work_orders:
        if wo.trade in [shift.trade for shift in shifts]:
            wo_by_wo = []
            for (wo_id, trade, day), decision_variable in x.items():
                if wo_id == wo.id:
                    wo_by_wo.append(decision_variable)

            model.Add(sum(wo_by_wo) <= 1)

    # Objective terms
    objective_terms = []

    # Objective 1: prioritize across several parameters based on gains for fine-tuning
    wo_by_id = {wo.id: wo for wo in work_orders}

    for (wo_id, trade, day), var in x.items():

        wo = wo_by_id.get(wo_id)

        type_as_int = 1 if wo.type == "Preventive maintenance" else 0
        safety_as_int = 1 if wo.safety else 0

        objective_terms.append(var *
                               (
                                   wo.age_days * objective_gains["age"] +
                                   (5-wo.priority) * objective_gains["priority"] +
                                   safety_as_int * objective_gains["safety"] +
                                   type_as_int * objective_gains["type"]
                               )
                               )
    # Objective 2: balance load across shifts
    for crew in shifts:
        manhours_per_shift = crew.technicians_per_crew*crew.shift_duration_hours
        sq_manhours_per_shift = manhours_per_shift**2

        for day in days:
            if crew.is_active_on_day(day):
                # list of manhours for this shift
                day_load = load_by_shift_and_day.get((crew.trade, day), [])
                # variable for total manhours for this shift using the equality constraint
                var_load = model.NewIntVar(
                    0, manhours_per_shift, f"var_load_{crew.trade}_{day}")
                model.Add(var_load == sum(day_load))

                # variable for the squared manhours for this shift using the equality constraint
                var_load_sq = model.NewIntVar(
                    0, manhours_per_shift**2, f"var_load_sq_{crew.trade}_{day}")
                model.AddMultiplicationEquality(
                    var_load_sq, [var_load, var_load])

                # add to objective function.  use difference from total squared manhours so we can maximize
                objective_terms.append(
                    (sq_manhours_per_shift - var_load_sq) * objective_gains["load_balance"])

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
