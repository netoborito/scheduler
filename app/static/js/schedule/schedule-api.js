/**
 * API calls and status. Depends: schedule-state.
 */
(function () {
  "use strict";
  const SchedulePage = window.SchedulePage;
  const state = SchedulePage.state;
  const Endpoints = window.Endpoints || {};

  /** Update the status bar text. */
  function setStatus(message) {
    const el = document.getElementById("status");
    if (el) el.textContent = message || "";
  }

  /** POST form data to the optimizer backend and return the JSON response. */
  async function postOptimize(formData) {
    const url = Endpoints.optimize || "/api/optimize";
    const response = await fetch(url, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) throw new Error("Optimization failed");
    return response.json();
  }

  const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

  /** Collect user-modified work orders into normalized records for hint payloads. */
  function buildHintRecords(includeScheduleDate) {
    const assignmentsById = new Map(
      state.latestSchedule.assignments.map((a) => [String(a.work_order_id), a])
    );
    const woById = new Map(state.latestWorkOrders.map((wo) => [String(wo.id), wo]));
    const scheduleStart = includeScheduleDate ? new Date(state.latestSchedule.start_date + "T00:00:00") : null;
    const records = [];

    for (const [id, wo] of woById.entries()) {
      const baseAssignment = assignmentsById.get(id) || null;
      const override = state.manualScheduleOverrides[id] || null;
      const isForcedUnscheduled = state.manualUnscheduledIds.has(id);
      const isForcedScheduled = state.manualScheduledIds.has(id);
      const isCurrentlyScheduled = !isForcedUnscheduled && (isForcedScheduled || !!baseAssignment);

      // Skip work orders the user hasn't touched; include overrides, forced-scheduled,
      // and forced-unscheduled so the optimizer gets both positive and negative hints.
      if (!override && !isForcedUnscheduled && !isForcedScheduled) continue;

      // Use the user's override when scheduled, otherwise fall back to the optimizer's
      // original assignment so negative hints still carry the original placement data.
      const effectiveAssignment = isCurrentlyScheduled ? (override || baseAssignment) : baseAssignment;
      const dayOffset = effectiveAssignment?.day_offset || 0;
      const idx = Math.max(0, Math.min(DAYS.length - 1, dayOffset));
      const dayName = DAYS[idx];
      const trade = override?.resource_id || baseAssignment?.resource_id || wo.trade || "";

      let scheduleDateStr = null;
      if (scheduleStart) {
        const scheduleDate = new Date(scheduleStart);
        scheduleDate.setDate(scheduleStart.getDate() + dayOffset);
        scheduleDateStr = SchedulePage.formatDateLocalYMD(scheduleDate);
      }

      // isCurrentlyScheduled = true are positive hints; isCurrentlyScheduled = false are negative hints.
      records.push({
        id: String(id),
        dayName,
        trade: String(trade),
        isCurrentlyScheduled,
        scheduleDate: scheduleDateStr,
      });
    }

    return records;
  }

  /** Shape hint records into the {id: [day, trade, scheduled]} dict the optimizer expects. */
  function buildHintsPayload() {
    const hints = {};
    for (const rec of buildHintRecords(false)) {
      hints[rec.id] = [rec.dayName, rec.trade, rec.isCurrentlyScheduled];
    }
    return hints;
  }

  /** Shape hint records into row objects for the /api/schedule/hints persistence endpoint. */
  function buildHintsExportRows() {
    return buildHintRecords(true).map((rec) => ({
      work_order_id: rec.id,
      schedule_date: rec.scheduleDate,
      trade: rec.trade,
      hint: rec.isCurrentlyScheduled ? 1 : 0,
    }));
  }

  /** Save current schedule state to localStorage and POST hint snapshot to backend. */
  function persistScheduleState() {
    if (typeof window === "undefined" || !window.localStorage) return;

    const payload = {
      weekStartDate: (state.latestSchedule && state.latestSchedule.start_date) || null,
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

    try {
      const rows = buildHintsExportRows();
      if (rows.length) {
        const hintsUrl = Endpoints.saveScheduleHints || "/api/schedule/hints";
        fetch(hintsUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(rows),
        }).catch(() => { });
      }
    } catch (_e) {
      // Ignore network errors
    }
  }

  /** Load schedule state from localStorage, discarding manual overrides if the week changed. */
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

    if (saved.latestSchedule) state.latestSchedule = saved.latestSchedule;
    if (Array.isArray(saved.latestWorkOrders)) state.latestWorkOrders = saved.latestWorkOrders;

    const currentWeekStart = document.getElementById("calendar")?.dataset?.defaultStart || null;
    const staleWeek = !saved.weekStartDate || saved.weekStartDate !== currentWeekStart;

    if (staleWeek) {
      state.manualScheduledIds = new Set();
      state.manualUnscheduledIds = new Set();
      state.manualScheduleOverrides = {};
    } else {
      state.manualScheduledIds = new Set(saved.manualScheduledIds || []);
      state.manualUnscheduledIds = new Set(saved.manualUnscheduledIds || []);
      state.manualScheduleOverrides = saved.manualScheduleOverrides || {};
    }
    state.shiftColors = saved.shiftColors || {};
    state.shiftAvailability = saved.shiftAvailability || [];
  }

  /** GET the backlog (work orders + shift metadata) without running the optimizer. */
  async function fetchBacklog() {
    const url = Endpoints.backlog || "/api/backlog";
    const response = await fetch(url);
    if (!response.ok) throw new Error("Failed to fetch backlog");
    return response.json();
  }

  /** POST the finalized schedule to the cloud EAM database. */
  async function postFinalizeSchedule() {
    const url = Endpoints.finalizeSchedule || "/api/schedule/finalize";
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        latestSchedule: state.latestSchedule,
        latestWorkOrders: state.latestWorkOrders,
      }),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error("Finalize failed: " + detail);
    }
    return response.json();
  }

  SchedulePage.setStatus = setStatus;
  SchedulePage.postOptimize = postOptimize;
  SchedulePage.postFinalizeSchedule = postFinalizeSchedule;
  SchedulePage.fetchBacklog = fetchBacklog;
  SchedulePage.buildHintsPayload = buildHintsPayload;
  SchedulePage.persistScheduleState = persistScheduleState;
  SchedulePage.restoreScheduleState = restoreScheduleState;
  SchedulePage.buildHintsExportRows = buildHintsExportRows;
})();
