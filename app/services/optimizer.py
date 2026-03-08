from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from datetime import date, timedelta

from ortools.sat.python import cp_model

from app.models.domain import WorkOrder, Assignment, Schedule
from app.models.shift import Shift
from app.services.shift_service import load_shifts
from app.utils.date_utils import get_next_monday

DAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

DEFAULT_OBJECTIVE_GAINS = {
    "age": 0.1,
    "priority": 1,
    "safety": 1,
    "type": 1,
    "load_balance": 1,
}


class ScheduleOptimizer:
    """Runs one scheduling optimization: builds model, adds constraints, solves, returns Schedule."""

    def __init__(
        self,
        work_orders: List[WorkOrder],
        start_date: Optional[date] = None,
        horizon_days: int = 7,
        objective_gains: Optional[Dict[str, float]] = None,
    ) -> None:
        self.work_orders = work_orders
        self.start_date = start_date
        self.horizon_days = horizon_days
        self.objective_gains = objective_gains or DEFAULT_OBJECTIVE_GAINS.copy()
        self.days = list(DAYS)
        self.model: cp_model.CpModel = cp_model.CpModel()
        self.shifts: List[Shift] = []
        self.x: Dict[Tuple[str, str, str], cp_model.BoolVar] = {}

    def optimize(self) -> Schedule:
        """Build model, solve, and return the schedule."""
        self.shifts = load_shifts()
        if not self.shifts:
            return Schedule(
                assignments=[],
                horizon_days=self.horizon_days,
                start_date=self.start_date,
            )

        self._create_decision_variables()
        self._schedule_forced_work_orders()
        self._add_shift_constraints()
        self.model.Maximize(self._sum_objective_terms())

        solver = cp_model.CpSolver()
        solver_status = solver.Solve(self.model)

        return self._build_schedule(solver, solver_status)

    def _create_decision_variables(self) -> None:
        for wo in self.work_orders:
            for shift in self.shifts:
                if shift.trade == wo.trade:
                    for day in self.days:
                        if shift.is_active_on_day(day):
                            self.x[wo.id, wo.trade, day] = (
                                self.model.NewBoolVar(f"x_{wo.id}_{wo.trade}_{day}")
                                * wo.duration_hours
                                * wo.num_people
                            )

    def _schedule_forced_work_orders(self) -> None:
        wo_by_id = {wo.id: wo for wo in self.work_orders}
        if self.start_date is None:
            return
        for (wo_id, trade, day), model_boolvar in self.x.items():
            wo = wo_by_id.get(wo_id)
            if wo is None:
                continue
            if wo.fixed and wo.schedule_date == self.start_date + timedelta(
                days=self.days.index(day)
            ):
                self.model.Add(model_boolvar == 1)

    def _add_shift_constraints(self) -> None:
        wo_by_id = {wo.id: wo for wo in self.work_orders}
        for shift in self.shifts:
            max_manhours_per_day = (
                shift.technicians_per_crew * shift.shift_duration_hours
            )
            for day in self.days:
                if shift.is_active_on_day(day):
                    shift_boolvars = self._get_shift_boolvars(day, shift)
                    shift_wo = []
                    for (wo_id, _st, _sd), expr in shift_boolvars.items():
                        shift_wo.append(expr)
                    if shift_wo:
                        self.model.Add(sum(shift_wo) <= max_manhours_per_day)

    def _get_shift_boolvars(
        self, day: str, shift: Shift
    ) -> Dict[Tuple[str, str, str], cp_model.BoolVar]:
        out: Dict[Tuple[str, str, str], cp_model.BoolVar] = {}
        for (wo_id, trade, sched_day), boolvar in self.x.items():
            if trade == shift.trade and sched_day == day:
                out[wo_id, trade, sched_day] = boolvar
        return out

    def _add_loadbalance_objective(self, gain: float = 1.0) -> List:
        objective_terms: List = []
        wo_by_id = {wo.id: wo for wo in self.work_orders}

        for crew in self.shifts:
            max_manhours_per_day = crew.technicians_per_crew * crew.shift_duration_hours
            sq_max_manhours_per_day = max_manhours_per_day**2

            for day in self.days:
                if crew.is_active_on_day(day):
                    boolvar_in_manhours_per_day: List = []
                    forced_manhours_per_day = 0

                    shift_boolvars = self._get_shift_boolvars(day, crew)
                    for (wo_id, _trade, _sched_day), boolvar in shift_boolvars.items():
                        wo = wo_by_id.get(wo_id)
                        if wo is not None and wo.fixed:
                            forced_manhours_per_day += wo.duration_hours * wo.num_people
                        boolvar_in_manhours_per_day.append(boolvar)

                    if forced_manhours_per_day > max_manhours_per_day:
                        max_manhours_per_day = forced_manhours_per_day
                        sq_max_manhours_per_day = forced_manhours_per_day**2

                    var_load = self.model.NewIntVar(
                        0,
                        max_manhours_per_day,
                        f"manhours_per_day_{crew.trade}_{day}",
                    )
                    self.model.Add(var_load == sum(boolvar_in_manhours_per_day))

                    var_load_sq = self.model.NewIntVar(
                        0,
                        sq_max_manhours_per_day,
                        f"manhours_per_day_sq_{crew.trade}_{day}",
                    )
                    self.model.AddMultiplicationEquality(
                        var_load_sq, [var_load, var_load]
                    )
                    objective_terms.append(
                        (sq_max_manhours_per_day - var_load_sq) * gain
                    )
        return objective_terms

    def _add_maximize_objective(self) -> List:
        maximize_terms: List = []
        wo_by_id = {wo.id: wo for wo in self.work_orders}
        gains = self.objective_gains

        for (wo_id, trade, day), var in self.x.items():
            wo = wo_by_id.get(wo_id)
            if wo is None:
                continue
            type_as_int = 1 if wo.type == "Preventive maintenance" else 0
            safety_as_int = 1 if wo.safety else 0
            maximize_terms.append(
                var
                * (
                    wo.age_days * gains["age"]
                    + (5 - wo.priority) * gains["priority"]
                    + safety_as_int * gains["safety"]
                    + type_as_int * gains["type"]
                )
            )
        return maximize_terms

    def _sum_objective_terms(self) -> cp_model.LinearExpr:
        balance_terms = self._add_loadbalance_objective(
            self.objective_gains["load_balance"]
        )
        maximize_terms = self._add_maximize_objective()
        return sum(maximize_terms + balance_terms)

    def _build_schedule(
        self, solver: cp_model.CpSolver, solver_status: int
    ) -> Schedule:
        assignments: List[Assignment] = []
        if solver_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for (wo_id, trade, day), var in self.x.items():
                if solver.Value(var) > 0.5:
                    assignments.append(
                        Assignment(
                            work_order_id=wo_id,
                            day_offset=self.days.index(day),
                            resource_id=trade,
                        )
                    )
        return Schedule(
            assignments=assignments,
            horizon_days=self.horizon_days,
            start_date=self.start_date,
        )


def optimize_schedule(
    work_orders: List[WorkOrder], start_date: Optional[date] = None
) -> Schedule:
    """Run the schedule optimizer and return the resulting schedule."""
    return ScheduleOptimizer(work_orders=work_orders, start_date=start_date).optimize()
