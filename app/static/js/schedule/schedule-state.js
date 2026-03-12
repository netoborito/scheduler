/**
 * Shared state for the schedule page. Load first.
 */
(function () {
  "use strict";
  window.SchedulePage = window.SchedulePage || {};
  window.SchedulePage.state = {
    calendar: null,
    latestSchedule: null,
    latestWorkOrders: [],
    scheduledSort: { key: "date", dir: "asc" },
    unscheduledSort: { key: "date", dir: "asc" },
    manualScheduledIds: new Set(),
    manualUnscheduledIds: new Set(),
    dragWoId: null,
    dragSource: null,
    allCalendarEvents: [],
    currentCalendarEvents: [],
    manualScheduleOverrides: {},
    shiftColors: {},
    shiftAvailability: [],
  };
})();
