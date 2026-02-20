from __future__ import annotations

from typing import List, Set
from datetime import date

from ortools.sat.python import cp_model

from app.models.domain import WorkOrder, Assignment, Schedule


HOURS_PER_DAY = 8.0


def optimize_schedule(
    work_orders: List[WorkOrder], 
    start_date: date | None = None
) -> Schedule:
    """Optimize schedule for a fixed 7-day horizon starting from start_date."""
    horizon_days = 7  # Fixed 7-day horizon
    """Optimize schedule using work order trades as resources."""
    model = cp_model.CpModel()

    # Extract unique trades from work orders (these are our resources)
    trades: Set[str] = {wo.trade for wo in work_orders}
    resources = sorted(list(trades))  # Sort for deterministic ordering
    
    if not resources:
        return Schedule(assignments=[], horizon_days=horizon_days)

    # Decision variables: x[wo.id][resource][day] = 1 if assigned
    # Only create variables for matching trades
    x = {}
    for wo in work_orders:
        # Only allow assignment to the trade required by this work order
        r = wo.trade
        for d in range(horizon_days):
            x[(wo.id, r, d)] = model.NewBoolVar(f"x_{wo.id}_{r}_{d}")

    # Each work order assigned at most once (single-day, single-resource)
    for wo in work_orders:
        r = wo.trade
        model.Add(
            sum(x[(wo.id, r, d)] for d in range(horizon_days)) <= 1
        )

    # Resource daily capacity (very simple: each WO consumes a full day if assigned)
    for r in resources:
        for d in range(horizon_days):
            # Sum all work orders of this trade assigned on this day
            model.Add(
                sum(
                    x[(wo.id, wo.trade, d)]
                    for wo in work_orders
                    if wo.trade == r
                )
                <= 1
            )

    # Objective: prioritize higher priority work orders earlier
    objective_terms = []
    for wo in work_orders:
        r = wo.trade
        for d in range(horizon_days):
            # Higher priority (larger number) and earlier days are preferred
            weight = wo.priority * (horizon_days - d)
            objective_terms.append(weight * x[(wo.id, r, d)])

    model.Maximize(sum(objective_terms))

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
    
    return Schedule(assignments=assignments, horizon_days=horizon_days, start_date=start_date)

