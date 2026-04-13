"""CP-SAT schedule optimizer for work order assignment."""

from __future__ import annotations

import csv
import os
import time
import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from app.models.domain import WorkOrder, Assignment, Schedule
from app.models.shift import Shift
from app.services.shift_service import load_shifts


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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
    "hints": 0,
}


class ScheduleOptimizer:
    """Runs one scheduling optimization: builds model, adds constraints, solves, returns Schedule."""

    def __init__(
        self,
        work_orders: List[WorkOrder],
        start_date: Optional[date] = None,
        horizon_days: int = 7,
        objective_gains: Optional[Dict[str, float]] = None,
        hints: Optional[Dict[str, Tuple[str, str, bool]]] = None,
    ) -> None:
        self.work_orders = work_orders
        self.start_date = start_date
        self.horizon_days = horizon_days
        self.objective_gains = objective_gains or DEFAULT_OBJECTIVE_GAINS
        self.days = list(DAYS)
        self.model: cp_model.CpModel = cp_model.CpModel()
        self.shifts: List[Shift] = []
        self.x: Dict[Tuple[str, str, str], cp_model.BoolVar] = {}
        self.time_scale: int = 2  # half-hour units so fractional durations become ints
        self.hints: Dict[str, Tuple[date, str, bool]] = hints or {}

    # -- Solve ---------------------------------------------------------------

    def optimize(self) -> Schedule:
        """Build model, solve, and return the schedule."""
        self.shifts = load_shifts()
        if not self.shifts:
            return Schedule(
                assignments=[],
                horizon_days=self.horizon_days,
                start_date=self.start_date,
            )

        csv_override = os.environ.get("OPTIMIZER_DEBUG_CSV", "").strip()
        csv_path = (
            Path(csv_override)
            if csv_override
            else Path(__file__).resolve().parent.parent.parent
            / "data"
            / "debug"
            / "optimizer_build_steps.csv"
        )
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not csv_path.is_file() or csv_path.stat().st_size == 0
        run_id = uuid.uuid4().hex[:8]

        def _ts() -> str:
            return datetime.now(timezone.utc).isoformat()

        with open(csv_path, "a", newline="", encoding="utf-8") as dbg_f:
            dbg_w = csv.writer(dbg_f)
            if write_header:
                dbg_w.writerow(
                    ["iso_timestamp", "run_id", "step", "elapsed_seconds", "num_x_vars"]
                )

            t0 = time.perf_counter()
            self._create_decision_variables()
            t1 = time.perf_counter()
            dbg_w.writerow([_ts(), run_id, "create_decision_variables", t1 - t0, len(self.x)])

            t0 = time.perf_counter()
            self._schedule_forced_work_orders()
            t1 = time.perf_counter()
            dbg_w.writerow([_ts(), run_id, "schedule_forced_work_orders", t1 - t0, len(self.x)])

            t0 = time.perf_counter()
            self._add_shift_constraints()
            t1 = time.perf_counter()
            dbg_w.writerow([_ts(), run_id, "add_shift_constraints", t1 - t0, len(self.x)])

            t0 = time.perf_counter()
            self._add_schedule_wo_once_constraint()
            t1 = time.perf_counter()
            dbg_w.writerow([_ts(), run_id, "add_schedule_wo_once_constraint", t1 - t0, len(self.x)])

            t0 = time.perf_counter()
            self.model.Maximize(self._sum_objective_terms())
            t1 = time.perf_counter()
            dbg_w.writerow([_ts(), run_id, "maximize_objective", t1 - t0, len(self.x)])

        solver = cp_model.CpSolver()
        # solver.parameters.max_time_in_seconds = 60
        solver_status = solver.Solve(self.model)

        return self._build_schedule(solver, solver_status)

    # -- Helpers -------------------------------------------------------------

    def _get_manhours(self, wo: WorkOrder) -> int:
        return int(round(max(wo.duration_hours, 0.5) * self.time_scale)) * wo.num_people

    # -- Constraints ---------------------------------------------------------

    def _add_schedule_wo_once_constraint(self) -> None:
        for wo in self.work_orders:
            if wo.trade in [shift.trade for shift in self.shifts]:
                wo_by_wo = []
                for (wo_id, trade, day), decision_variable in self.x.items():
                    if wo_id == wo.id:
                        wo_by_wo.append(decision_variable)
                self.model.Add(sum(wo_by_wo) <= 1)

    def _get_shift_boolvars(
        self, day: str, shift: Shift
    ) -> Dict[Tuple[str, str, str], cp_model.BoolVar]:
        out: Dict[Tuple[str, str, str], cp_model.BoolVar] = {}
        for (wo_id, trade, sched_day), boolvar in self.x.items():
            if trade == shift.trade and sched_day == day:
                out[wo_id, trade, sched_day] = boolvar
        return out

    def _create_decision_variables(self) -> None:
        for wo in self.work_orders:
            for shift in self.shifts:
                if shift.trade == wo.trade:
                    for day in self.days:
                        if shift.is_active_on_day(day):
                            boolvar = self.model.NewBoolVar(
                                f"x_{wo.id}_{wo.trade}_{day}"
                            )
                            self.x[wo.id, wo.trade, day] = boolvar

    def _schedule_forced_work_orders(self) -> None:
        wo_by_id = {wo.id: wo for wo in self.work_orders}
        if self.start_date is None:
            return
        for (wo_id, _trade, day), boolvar in self.x.items():
            wo = wo_by_id.get(wo_id)
            if wo is None:
                continue
            if wo.fixed and wo.schedule_date == self.start_date + timedelta(
                days=self.days.index(day)
            ):
                self.model.Add(boolvar == 1)

    def _add_shift_constraints(self) -> None:
        wo_by_id = {wo.id: wo for wo in self.work_orders}

        for shift in self.shifts:
            max_manhours_per_day = (
                shift.technicians_per_crew
                * shift.shift_duration_hours
                * self.time_scale
            )
            for day in self.days:
                if shift.is_active_on_day(day):
                    shift_boolvars = self._get_shift_boolvars(day, shift)
                    shift_wo = []
                    total_units = 0

                    for (wo_id, _, _), boolvar in shift_boolvars.items():
                        manhours = self._get_manhours(wo_by_id[wo_id])
                        shift_wo.append(boolvar * manhours)
                        total_units += manhours

                    if shift_wo:
                        self.model.Add(sum(shift_wo) <= max_manhours_per_day)

    # -- Objective -----------------------------------------------------------

    def _add_loadbalance_objective(self, gain: float = 1.0) -> List:
        objective_terms: List = []
        wo_by_id = {wo.id: wo for wo in self.work_orders}

        for crew in self.shifts:
            max_manhours_per_day = (
                crew.technicians_per_crew * crew.shift_duration_hours * self.time_scale
            )
            sq_max_manhours_per_day = max_manhours_per_day**2

            for day in self.days:
                if crew.is_active_on_day(day):
                    boolvar_in_manhours_per_day: List = []
                    forced_manhours_per_day = 0

                    shift_boolvars = self._get_shift_boolvars(day, crew)
                    for (wo_id, _trade, _sched_day), boolvar in shift_boolvars.items():
                        wo = wo_by_id.get(wo_id)

                        manhours = self._get_manhours(wo)
                        if wo is not None and wo.fixed:
                            forced_manhours_per_day += manhours
                        boolvar_in_manhours_per_day.append(boolvar * manhours)

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
                        (var_load_sq - sq_max_manhours_per_day) * gain
                    )
        return objective_terms

    def _add_maximize_objective(self) -> List:
        maximize_terms: List = []
        wo_by_id = {wo.id: wo for wo in self.work_orders}
        gains = self.objective_gains

        for (wo_id, trade, day), var in self.x.items():
            wo = wo_by_id[wo_id]
            type_as_int = 1 if wo.type == "Preventive maintenance" else 0
            safety_as_int = 1 if wo.safety else 0
            hint = self._is_hint(wo_id, trade, day)

            maximize_terms.append(
                var
                * (
                    wo.age_days * gains["age"]
                    + (5 - wo.priority) * gains["priority"]
                    + safety_as_int * gains["safety"]
                    + type_as_int * gains["type"]
                    # + hint * gains["hints"]
                )
            )
        return maximize_terms

    def _is_hint(self, wo_id: str, trade: str, day: str) -> int:
        if wo_id in self.hints.keys():
            if (
                self.hints[wo_id][0] == day
                and self.hints[wo_id][1] == trade
                and self.hints[wo_id][2] == True
            ):
                return 1
            else:
                return -1
        else:
            return 0

    def _sum_objective_terms(self) -> cp_model.LinearExpr:
        balance_terms = self._add_loadbalance_objective(
            self.objective_gains["load_balance"]
        )
        maximize_terms = self._add_maximize_objective()
        return sum(maximize_terms + balance_terms)

    # -- Result --------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_bzus_preferences(work_orders: List[WorkOrder]) -> List[WorkOrder]:
    """Remap trades for BZ unit work orders based on equipment prefix."""
    result = []
    for wo in work_orders:
        if wo.dept == "0400" or wo.dept == "0500":
            is_bz = True
        else:
            is_bz = False

        if wo.trade == "NC-E/I" and is_bz:
            wo = replace(wo, trade="NC-E/I PM")
        elif wo.trade == "NC-MECHANIC" and is_bz:
            wo = replace(wo, trade="NC-PM NIGHT")
        elif wo.trade == "NC-MECHANIC":
            wo = replace(wo, trade="NC-PM DAY")
        result.append(wo)
    return result


def optimize_schedule(
    work_orders: List[WorkOrder],
    start_date: Optional[date] = None,
    hints: Optional[Dict[str, Tuple[date, str, bool]]] = None,
    objective_gains: Optional[Dict[str, float]] = None,
) -> Schedule:
    """Run the schedule optimizer and return the resulting schedule."""
    # work_orders = apply_bzus_preferences(work_orders)

    return ScheduleOptimizer(
        work_orders=work_orders,
        start_date=start_date,
        hints=hints,
        objective_gains=objective_gains,
    ).optimize()
