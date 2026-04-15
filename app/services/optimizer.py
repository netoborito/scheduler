"""CP-SAT schedule optimizer for work order assignment."""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from app.models.domain import WorkOrder, Assignment, Schedule
from app.models.shift import Shift
from app.services.preferences_service import load_preferences
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
    "load_balance": 2,
    "hints": 1,
    "schedule_bonus": 10,
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

        self._create_decision_variables()
        self._schedule_forced_work_orders()
        self._add_shift_constraints()
        self._add_schedule_wo_once_constraint()
        self.model.Maximize(self._sum_objective_terms())

        solver = cp_model.CpSolver()
        # solver.parameters.max_time_in_seconds = 100
        solver_status = solver.Solve(self.model)

        return self._build_schedule(solver, solver_status)

    # -- Helpers -------------------------------------------------------------

    def _get_manhours(self, wo: WorkOrder) -> int:
        return int(round(max(wo.duration_hours, 0.5) * self.time_scale)) * wo.num_people

    # -- Constraints ---------------------------------------------------------

    def _add_schedule_wo_once_constraint(self) -> None:
        debug_rows: List[List] = []
        for wo in self.work_orders:
            if wo.trade in [shift.trade for shift in self.shifts]:
                wo_by_wo = []
                for (wo_id, trade, day), decision_variable in self.x.items():
                    if wo_id == wo.id:
                        wo_by_wo.append(decision_variable)
                self.model.Add(sum(wo_by_wo) <= 1)
                debug_rows.append([wo.id, wo.trade, len(wo_by_wo), str(wo_by_wo)])

        if os.environ.get("OPTIMIZER_DEBUG_CSV", "").strip() and debug_rows:
            with open(
                "data/debug/schedule_wo_once_constraints.csv",
                "w",
                newline="",
                encoding="utf-8",
            ) as f:
                w = csv.writer(f)
                w.writerow(["wo_id", "trade", "num_vars", "boolvars"])
                w.writerows(debug_rows)

    def _get_shift_boolvars(
        self, day: str, shift: Shift
    ) -> Dict[Tuple[str, str, str], cp_model.BoolVar]:
        out: Dict[Tuple[str, str, str], cp_model.BoolVar] = {}
        for (wo_id, trade, sched_day), boolvar in self.x.items():
            if trade == shift.trade and sched_day == day:
                out[wo_id, trade, sched_day] = boolvar
        return out

    def _create_decision_variables(self) -> None:
        debug_rows: List[List] = []
        for wo in self.work_orders:
            for shift in self.shifts:
                if shift.trade == wo.trade:
                    for day in self.days:
                        if shift.is_active_on_day(day):
                            boolvar = self.model.NewBoolVar(
                                f"x_{wo.id}_{wo.trade}_{day}"
                            )
                            self.x[wo.id, wo.trade, day] = boolvar
                            debug_rows.append([wo.id, wo.trade, day, str(boolvar)])

        if os.environ.get("OPTIMIZER_DEBUG_CSV", "").strip() and debug_rows:
            with open(
                "data/debug/decision_variables.csv",
                "w",
                newline="",
                encoding="utf-8",
            ) as f:
                w = csv.writer(f)
                w.writerow(["wo_id", "trade", "day", "boolvar"])
                w.writerows(debug_rows)

    def _schedule_forced_work_orders(self) -> None:
        wo_by_id = {wo.id: wo for wo in self.work_orders}
        if self.start_date is None:
            return
        debug_rows: List[List] = []
        for (wo_id, _trade, day), boolvar in self.x.items():
            wo = wo_by_id.get(wo_id)
            if wo is None:
                continue
            if wo.fixed and wo.schedule_date == self.start_date + timedelta(
                days=self.days.index(day)
            ):
                self.model.Add(boolvar == 1)
                debug_rows.append([wo_id, _trade, day, str(boolvar)])

        if os.environ.get("OPTIMIZER_DEBUG_CSV", "").strip() and debug_rows:
            with open(
                "data/debug/forced_work_orders.csv",
                "w",
                newline="",
                encoding="utf-8",
            ) as f:
                w = csv.writer(f)
                w.writerow(["wo_id", "trade", "day", "boolvar"])
                w.writerows(debug_rows)

    def _add_shift_constraints(self) -> None:
        wo_by_id = {wo.id: wo for wo in self.work_orders}
        debug_rows: List[List] = []

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
                        debug_rows.append(
                            [
                                shift.trade,
                                day,
                                total_units,
                                max_manhours_per_day,
                                str(shift_wo),
                            ]
                        )

        if os.environ.get("OPTIMIZER_DEBUG_CSV", "").strip() and debug_rows:
            with open(
                "data/debug/shift_constraints.csv",
                "w",
                newline="",
                encoding="utf-8",
            ) as f:
                w = csv.writer(f)
                w.writerow(
                    ["shift", "day", "total_units", "max_manhours_per_day", "shift_wo"]
                )
                w.writerows(debug_rows)

    # -- Objective -----------------------------------------------------------

    def _add_loadbalance_objective_linear(self, gain: float = 1.0) -> List:
        """Minimax load-balance: penalize the peak daily load per shift."""
        objective_terms: List = []
        debug_rows: List[List] = []
        wo_by_id = {wo.id: wo for wo in self.work_orders}

        for crew in self.shifts:
            max_manhours_per_day = int(
                crew.technicians_per_crew * crew.shift_duration_hours * self.time_scale
            )

            max_load_var = self.model.NewIntVar(
                0, max_manhours_per_day, f"max_load_{crew.trade}"
            )

            for day in self.days:
                if crew.is_active_on_day(day):
                    boolvar_in_manhours_per_day: List = []

                    shift_boolvars = self._get_shift_boolvars(day, crew)
                    for (wo_id, _trade, _sched_day), boolvar in shift_boolvars.items():
                        wo = wo_by_id.get(wo_id)
                        if wo is not None and wo.fixed:
                            continue
                        manhours = self._get_manhours(wo)
                        boolvar_in_manhours_per_day.append(boolvar * manhours)

                    var_load = self.model.NewIntVar(
                        0,
                        max_manhours_per_day,
                        f"lin_load_{crew.trade}_{day}",
                    )
                    self.model.Add(var_load == sum(boolvar_in_manhours_per_day))
                    self.model.Add(max_load_var >= var_load)

            objective_terms.append(-max_load_var * gain)
            debug_rows.append([crew.trade, str(max_load_var)])

        if os.environ.get("OPTIMIZER_DEBUG_CSV") == "1" and debug_rows:
            with open(
                "data/debug/loadbalance_linear_terms.csv",
                "w",
                newline="",
                encoding="utf-8",
            ) as f:
                w = csv.writer(f)
                w.writerow(["trade", "max_load_var"])
                w.writerows(debug_rows)

        return objective_terms

    def _add_maximize_objective(self) -> List:
        maximize_terms: List = []
        wo_by_id = {wo.id: wo for wo in self.work_orders}
        gains = self.objective_gains
        max_wo_manhours = max(
            (self._get_manhours(wo) for wo in self.work_orders), default=0
        )
        schedule_bonus = max_wo_manhours * gains["schedule_bonus"]

        for (wo_id, trade, day), var in self.x.items():
            wo = wo_by_id[wo_id]
            type_as_int = 1 if wo.type == "Preventive maintenance" else 0
            safety_as_int = 1 if wo.safety else 0
            hint = self._is_hint(wo_id, trade, day)

            maximize_terms.append(
                var
                * (
                    schedule_bonus
                    + wo.age_days * gains["age"]
                    + (5 - wo.priority) * gains["priority"]
                    + safety_as_int * gains["safety"]
                    + type_as_int * gains["type"]
                    + hint * gains["hints"]
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
        balance_terms = self._add_loadbalance_objective_linear(
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


def apply_custom_preferences(work_orders: List[WorkOrder]) -> List[WorkOrder]:
    """Apply data-driven match/set rules from preferences.json to remap WO fields."""
    rules = load_preferences()
    if not rules:
        return work_orders

    out: List[WorkOrder] = []
    for wo in work_orders:
        matched = False
        for rule in rules:
            if all(
                re.search(pattern, str(getattr(wo, field, "")))
                for field, pattern in rule["match"].items()
            ):
                out.append(replace(wo, **rule["set"]))
                matched = True
                break
        if not matched:
            out.append(wo)
    return out


def optimize_schedule(
    work_orders: List[WorkOrder],
    start_date: Optional[date] = None,
    hints: Optional[Dict[str, Tuple[date, str, bool]]] = None,
    objective_gains: Optional[Dict[str, float]] = None,
) -> Schedule:
    """Run the schedule optimizer and return the resulting schedule."""
    work_orders = apply_custom_preferences(work_orders)

    hint_ids = set(hints or {})
    horizon_end = start_date + timedelta(days=7) if start_date else None
    current_week_start = start_date - timedelta(days=7) if start_date else None

    direct_wos: List[WorkOrder] = []
    optimizer_wos: List[WorkOrder] = []
    for wo in work_orders:
        is_current_week = (
            wo.schedule_date
            and start_date
            and current_week_start <= wo.schedule_date < start_date
        )
        is_beyond_horizon_pm = (
            wo.type == "Preventive maintenance"
            and wo.schedule_date
            and horizon_end
            and wo.schedule_date >= horizon_end
            and wo.id not in hint_ids
        )
        if is_current_week or is_beyond_horizon_pm:
            direct_wos.append(wo)
        else:
            optimizer_wos.append(wo)

    schedule = ScheduleOptimizer(
        work_orders=optimizer_wos,
        start_date=start_date,
        hints=hints,
        objective_gains=objective_gains,
    ).optimize()

    for wo in direct_wos:
        day_offset = (wo.schedule_date - start_date).days
        schedule.assignments.append(
            Assignment(
                work_order_id=str(wo.id),
                day_offset=day_offset,
                resource_id=wo.trade,
            )
        )

    return schedule
