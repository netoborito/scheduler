/**
 * API calls and status. Depends: schedule-state.
 */
(function () {
  "use strict";
  const SchedulePage = window.SchedulePage;

  function setStatus(message) {
    const el = document.getElementById("status");
    if (el) el.textContent = message || "";
  }

  async function postOptimize(formData) {
    const response = await fetch("/api/optimize", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) throw new Error("Optimization failed");
    return response.json();
  }

  function buildHintsPayload() {
    const state = SchedulePage.state;
    if (!state || !state.latestSchedule || !state.latestWorkOrders || !state.latestWorkOrders.length) {
      return {};
    }

    const hints = {};
    const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

    const assignmentsById = new Map(
      (state.latestSchedule.assignments || []).map((a) => [String(a.work_order_id), a])
    );
    const woById = new Map(state.latestWorkOrders.map((wo) => [String(wo.id), wo]));

    for (const [id, wo] of woById.entries()) {
      const baseAssignment = assignmentsById.get(id) || null;
      const override = state.manualScheduleOverrides[id] || null;
      const isForcedUnscheduled = state.manualUnscheduledIds.has(id);
      const isForcedScheduled = state.manualScheduledIds.has(id);
      const hasAnyAssignment = !!baseAssignment;

      const isCurrentlyScheduled = !isForcedUnscheduled && (isForcedScheduled || hasAnyAssignment);

      if (isCurrentlyScheduled) {
        const dayOffset =
          override && typeof override.day_offset === "number"
            ? override.day_offset
            : baseAssignment
            ? Number(baseAssignment.day_offset || 0)
            : 0;
        const trade =
          (override && override.resource_id) ||
          (baseAssignment && baseAssignment.resource_id) ||
          wo.trade ||
          "";

        const idx = Math.max(0, Math.min(DAYS.length - 1, Number(dayOffset) || 0));
        const dayName = DAYS[idx];

        hints[id] = [dayName, String(trade), true];
      } else if (baseAssignment) {
        const dayOffset = Number(baseAssignment.day_offset || 0);
        const trade = baseAssignment.resource_id || wo.trade || "";
        const idx = Math.max(0, Math.min(DAYS.length - 1, Number(dayOffset) || 0));
        const dayName = DAYS[idx];

        hints[id] = [dayName, String(trade), false];
      }
    }

    return hints;
  }

  function buildHintsExportRows() {
    const state = SchedulePage.state;
    if (
      !state ||
      !state.latestSchedule ||
      !state.latestSchedule.start_date ||
      !state.latestWorkOrders ||
      !state.latestWorkOrders.length
    ) {
      return [];
    }

    const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
    const assignmentsById = new Map(
      (state.latestSchedule.assignments || []).map((a) => [String(a.work_order_id), a])
    );
    const woById = new Map(state.latestWorkOrders.map((wo) => [String(wo.id), wo]));
    const scheduleStart = new Date(state.latestSchedule.start_date + "T00:00:00");
    const rows = [];

    for (const [id, wo] of woById.entries()) {
      const baseAssignment = assignmentsById.get(id) || null;
      const override = state.manualScheduleOverrides[id] || null;
      const isForcedUnscheduled = state.manualUnscheduledIds.has(id);
      const isForcedScheduled = state.manualScheduledIds.has(id);
      const hasAnyAssignment = !!baseAssignment;

      const isCurrentlyScheduled = !isForcedUnscheduled && (isForcedScheduled || hasAnyAssignment);

      if (!baseAssignment && !isCurrentlyScheduled) {
        continue;
      }

      const effectiveAssignment = isCurrentlyScheduled ? (override || baseAssignment) : baseAssignment;
      const dayOffset =
        effectiveAssignment && typeof effectiveAssignment.day_offset === "number"
          ? Number(effectiveAssignment.day_offset || 0)
          : 0;
      const trade =
        (override && override.resource_id) ||
        (baseAssignment && baseAssignment.resource_id) ||
        wo.trade ||
        "";

      const scheduleDate = new Date(scheduleStart);
      scheduleDate.setDate(scheduleStart.getDate() + dayOffset);
      const scheduleDateStr = SchedulePage.formatDateLocalYMD(scheduleDate);

      const idx = Math.max(0, Math.min(DAYS.length - 1, Number(dayOffset) || 0));
      const dayName = DAYS[idx];
      const hintFlag = isCurrentlyScheduled ? 1 : 0;

      rows.push({
        work_order_id: String(id),
        schedule_date: scheduleDateStr,
        trade: String(trade),
        hint: hintFlag,
      });
    }

    return rows;
  }

  function persistScheduleState() {
    try {
      if (typeof window === "undefined" || !window.localStorage) return;
    } catch (_e) {
      return;
    }
    const state = SchedulePage.state;
    if (!state) return;
    const payload = {
      latestSchedule: state.latestSchedule,
      latestWorkOrders: state.latestWorkOrders,
      manualScheduledIds: Array.from(state.manualScheduledIds || []),
      manualUnscheduledIds: Array.from(state.manualUnscheduledIds || []),
      manualScheduleOverrides: state.manualScheduleOverrides || {},
      shiftColors: state.shiftColors || {},
      shiftAvailability: state.shiftAvailability || [],
    };
    try {
      window.localStorage.setItem("schedule_state_v1", JSON.stringify(payload));
    } catch (_e) {
      // Ignore storage errors
    }

    // Fire-and-forget save of hints snapshot to backend for optimizer.
    if (SchedulePage.buildHintsExportRows) {
      try {
        const rows = SchedulePage.buildHintsExportRows();
        if (rows && rows.length) {
          fetch("/api/schedule/hints", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(rows),
          }).catch(() => {});
        }
      } catch (_e) {
        // Ignore network errors
      }
    }
  }

  function restoreScheduleState() {
    let raw = null;
    try {
      if (typeof window === "undefined" || !window.localStorage) return;
      raw = window.localStorage.getItem("schedule_state_v1");
    } catch (_e) {
      return;
    }
    if (!raw) return;
    let saved;
    try {
      saved = JSON.parse(raw);
    } catch (_e) {
      return;
    }
    if (!saved || typeof saved !== "object") return;
    const state = SchedulePage.state;
    if (!state) return;

    if (saved.latestSchedule) state.latestSchedule = saved.latestSchedule;
    if (Array.isArray(saved.latestWorkOrders)) state.latestWorkOrders = saved.latestWorkOrders;
    state.manualScheduledIds = new Set(saved.manualScheduledIds || []);
    state.manualUnscheduledIds = new Set(saved.manualUnscheduledIds || []);
    state.manualScheduleOverrides = saved.manualScheduleOverrides || {};
    state.shiftColors = saved.shiftColors || {};
    state.shiftAvailability = saved.shiftAvailability || [];
  }

  SchedulePage.setStatus = setStatus;
  SchedulePage.postOptimize = postOptimize;
  SchedulePage.buildHintsPayload = buildHintsPayload;
  SchedulePage.persistScheduleState = persistScheduleState;
  SchedulePage.restoreScheduleState = restoreScheduleState;
  SchedulePage.buildHintsExportRows = buildHintsExportRows;
})();
