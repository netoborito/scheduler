/**
 * API calls and status. Depends: schedule-state.
 */
(function () {
  "use strict";
  const SchedulePage = window.SchedulePage;
  const Endpoints = window.Endpoints || {};

  function setStatus(message) {
    const el = document.getElementById("status");
    if (el) el.textContent = message || "";
  }

  async function postOptimize(formData) {
    const url = Endpoints.optimize || "/api/optimize";
    const response = await fetch(url, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const errText = await response.text();
      // #region agent log
      fetch('http://127.0.0.1:7640/ingest/7a3dd2d9-a345-4784-8f89-4cb4e0b15ff3',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'f98a82'},body:JSON.stringify({sessionId:'f98a82',runId:'pre-fix',hypothesisId:'H1-H4',location:'schedule-api.js:22',message:'postOptimize non-OK response',data:{status:response.status,statusText:response.statusText,body:errText.slice(0,1000)},timestamp:Date.now()})}).catch(()=>{});
      // #endregion
      throw new Error("Optimization failed");
    }
    return response.json();
  }

  const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

  function buildHintRecords(includeScheduleDate) {
    const state = SchedulePage.state;
    if (!state || !state.latestSchedule || !state.latestWorkOrders || !state.latestWorkOrders.length) {
      return [];
    }
    if (includeScheduleDate && !state.latestSchedule.start_date) {
      return [];
    }

    // Build the assignments by ID map
    const assignmentsById = new Map(
      (state.latestSchedule.assignments || []).map((a) => [String(a.work_order_id), a])
    );
    const woById = new Map(state.latestWorkOrders.map((wo) => [String(wo.id), wo]));
    // Get the schedule start date
    const scheduleStart = includeScheduleDate ? new Date(state.latestSchedule.start_date + "T00:00:00") : null;
    const records = [];

    // Loop through the work orders
    for (const [id, wo] of woById.entries()) {
      const baseAssignment = assignmentsById.get(id) || null;
      const override = state.manualScheduleOverrides[id] || null;
      const isForcedUnscheduled = state.manualUnscheduledIds.has(id);
      const isForcedScheduled = state.manualScheduledIds.has(id);
      const hasAnyAssignment = !!baseAssignment;
      const isCurrentlyScheduled = !isForcedUnscheduled && (isForcedScheduled || hasAnyAssignment);

      if (!baseAssignment && !isCurrentlyScheduled) continue;

      const effectiveAssignment = isCurrentlyScheduled ? (override || baseAssignment) : baseAssignment;
      const dayOffset =
        effectiveAssignment && typeof effectiveAssignment.day_offset === "number"
          ? Number(effectiveAssignment.day_offset || 0)
          : 0;
      const idx = Math.max(0, Math.min(DAYS.length - 1, Number(dayOffset) || 0));
      const dayName = DAYS[idx];
      const trade =
        (override && override.resource_id) ||
        (baseAssignment && baseAssignment.resource_id) ||
        wo.trade ||
        "";

      let scheduleDateStr = null;
      if (scheduleStart) {
        const scheduleDate = new Date(scheduleStart);
        scheduleDate.setDate(scheduleStart.getDate() + dayOffset);
        scheduleDateStr = SchedulePage.formatDateLocalYMD(scheduleDate);
      }

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

  function buildHintsPayload() {
    const hints = {};
    for (const rec of buildHintRecords(false)) {
      hints[rec.id] = [rec.dayName, rec.trade, rec.isCurrentlyScheduled];
    }
    return hints;
  }

  function buildHintsExportRows() {
    return buildHintRecords(true).map((rec) => ({
      work_order_id: rec.id,
      schedule_date: rec.scheduleDate,
      trade: rec.trade,
      hint: rec.isCurrentlyScheduled ? 1 : 0,
    }));
  }

  // Save the current schedule state to local storage
  function persistScheduleState() {

    // Check if the local storage is available
    if (typeof window === "undefined" || !window.localStorage) return;

    // Get the current schedule state
    const state = SchedulePage.state;
    if (!state) return;

    // Build the payload
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

    // Save the hints snapshot to the backend for the optimizer.
    if (SchedulePage.buildHintsExportRows) {
      try {
        // Build the hints export rows
        const rows = SchedulePage.buildHintsExportRows();

        // If there are any rows, save the hints to the backend
        if (rows && rows.length) {
          // Get the hints URL
          const hintsUrl = Endpoints.saveScheduleHints || "/api/schedule/hints";

          // Save the hints to the backend
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
