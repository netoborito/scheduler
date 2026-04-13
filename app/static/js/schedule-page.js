/**
 * Schedule page entry point. Initializes form, resource filter, sorting, drag-drop.
 * Depends: schedule-state, schedule-utils, schedule-shifts, schedule-calendar, schedule-tables, schedule-api.
 */
(function () {
  "use strict";
  const SchedulePage = window.SchedulePage;
  const state = SchedulePage.state;
  const Endpoints = window.Endpoints || {};

  // Initialize the form handlers
  function initFormHandlers() {
    // optimize form & submit handler
    const form = document.getElementById("optimize-form");
    if (form) {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const fd = new FormData();
        // If there is a buildHintsPayload function, build the hints payload
        if (SchedulePage.buildHintsPayload) {
          // Build the hints payload
          const hints = SchedulePage.buildHintsPayload();
          // If the hints payload is not empty, append the hints to the form data
          if (hints && Object.keys(hints).length > 0) {
            fd.append("hints_json", JSON.stringify(hints));
          }
        }
        try {
          // Set the status to optimizing schedule
          SchedulePage.setStatus("Optimizing schedule...");
          // Post the optimize request (backend python function)
          const data = await SchedulePage.postOptimize(fd);
          // Update state with the latest schedule and work orders
          state.latestSchedule = data.schedule || null;
          state.latestWorkOrders = data.work_orders || [];
          state.shiftColors = data.shift_colors || {};
          state.shiftAvailability = data.shift_availability || [];
          state.manualScheduleOverrides = {};
          SchedulePage.populateResourceSelect(state.latestSchedule, state.latestWorkOrders);
          SchedulePage.rebuildAllCalendarEvents();

          if (!state.calendar) {
            SchedulePage.initCalendar();
          }
          if (state.calendar) {
            try {
              const horizonDays = data.schedule.horizon_days || 7;
              const rangeStart = data.schedule.start_date;
              const rangeEndDate = new Date(data.schedule.start_date + "T00:00:00");
              rangeEndDate.setDate(rangeEndDate.getDate() + Number(horizonDays || 7));
              const rangeEnd = SchedulePage.formatDateLocalYMD(rangeEndDate);
              state.calendar.setOption("visibleRange", { start: rangeStart, end: rangeEnd });
              state.calendar.changeView("dayGridWeek", rangeStart);
            } catch (e) {
              console.error("Failed to set calendar visibleRange", e);
            }
            SchedulePage.applyCalendarResourceFilter();
          }
          SchedulePage.setStatus(
            "Scheduled " + state.allCalendarEvents.length + " assignments over 7 days starting " + data.schedule.start_date + "."
          );
          SchedulePage.updateTradeViews();
          if (SchedulePage.persistScheduleState) {
            SchedulePage.persistScheduleState();
          }
        } catch (err) {
          console.error(err);
          SchedulePage.setStatus("Error during optimization. See console for details.");
        }
      });
    }

    const downloadBtn = document.getElementById("download-xlsx-btn");
    if (downloadBtn) {
      downloadBtn.addEventListener("click", async () => {
        if (!state.latestSchedule || !state.latestWorkOrders || !state.latestWorkOrders.length) {
          alert("Generate a schedule first before downloading .xlsx.");
          return;
        }
        try {
          SchedulePage.setStatus("Generating schedule .xlsx...");
          const optimizeXlsxUrl = Endpoints.optimizeXlsx || "/api/optimize/xlsx";
          const response = await fetch(optimizeXlsxUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              latestSchedule: state.latestSchedule,
              latestWorkOrders: state.latestWorkOrders,
            }),
          });
          if (!response.ok) throw new Error("Failed to generate .xlsx");
          const blob = await response.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "schedule.xlsx";
          document.body.appendChild(a);
          a.click();
          a.remove();
          window.URL.revokeObjectURL(url);
          SchedulePage.setStatus("Downloaded schedule.xlsx.");
        } catch (err) {
          console.error(err);
          SchedulePage.setStatus("Error generating .xlsx. See console for details.");
        }
      });
    }
  }

  function initResourceFilter() {
    const select = document.getElementById("resource-select");
    if (select) {
      select.addEventListener("change", () => {
        SchedulePage.updateTradeViews();
        SchedulePage.applyCalendarResourceFilter();
      });
    }
  }

  function initSorting() {
    document.querySelectorAll("th[data-table='scheduled']").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.getAttribute("data-key");
        if (!key) return;
        if (state.scheduledSort.key === key) {
          state.scheduledSort.dir = state.scheduledSort.dir === "asc" ? "desc" : "asc";
        } else {
          state.scheduledSort.key = key;
          state.scheduledSort.dir = "asc";
        }
        SchedulePage.updateTradeViews();
      });
    });
    document.querySelectorAll("th[data-table='unscheduled']").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.getAttribute("data-key");
        if (!key) return;
        if (state.unscheduledSort.key === key) {
          state.unscheduledSort.dir = state.unscheduledSort.dir === "asc" ? "desc" : "asc";
        } else {
          state.unscheduledSort.key = key;
          state.unscheduledSort.dir = "asc";
        }
        SchedulePage.updateTradeViews();
      });
    });
  }

  function initDragDrop() {
    const scheduledBody = document.getElementById("scheduled-tbody");
    const unscheduledBody = document.getElementById("unscheduled-tbody");

    function handleDropToScheduled(e) {
      e.preventDefault();
      const id = e.dataTransfer.getData("text/plain") || state.dragWoId;
      if (!id) return;
      state.manualUnscheduledIds.delete(id);
      state.manualScheduledIds.add(id);
      SchedulePage.updateTradeViews();
      if (SchedulePage.persistScheduleState) {
        SchedulePage.persistScheduleState();
      }
    }

    function handleDropToUnscheduled(e) {
      e.preventDefault();
      if (state.dragSource === "unscheduled") return;
      const id = e.dataTransfer.getData("text/plain") || state.dragWoId;
      if (!id) return;
      state.manualScheduledIds.delete(id);
      state.manualUnscheduledIds.add(id);
      SchedulePage.rebuildAllCalendarEvents();
      SchedulePage.applyCalendarResourceFilter();
      SchedulePage.updateTradeViews();
      if (SchedulePage.persistScheduleState) {
        SchedulePage.persistScheduleState();
      }
    }

    if (scheduledBody) {
      scheduledBody.addEventListener("dragover", (e) => {
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
      });
      scheduledBody.addEventListener("drop", handleDropToScheduled);
    }
    if (unscheduledBody) {
      unscheduledBody.addEventListener("dragover", (e) => {
        e.preventDefault();
        if (e.dataTransfer) {
          e.dataTransfer.dropEffect =
            state.dragSource === "calendar" || state.dragSource === "scheduled" ? "move" : "none";
        }
      });
      unscheduledBody.addEventListener("drop", handleDropToUnscheduled);
    }
  }

  function initSchedulePage() {
    if (SchedulePage.restoreScheduleState) {
      SchedulePage.restoreScheduleState();
    }
    SchedulePage.initCalendar();
    initFormHandlers();
    initResourceFilter();
    initSorting();
    initDragDrop();

    if (state.latestSchedule && state.latestWorkOrders && state.latestWorkOrders.length) {
      SchedulePage.populateResourceSelect(state.latestSchedule, state.latestWorkOrders);
      SchedulePage.rebuildAllCalendarEvents();
      if (state.calendar && state.latestSchedule.start_date) {
        try {
          const horizonDays = state.latestSchedule.horizon_days || 7;
          const rangeStart = state.latestSchedule.start_date;
          const rangeEndDate = new Date(state.latestSchedule.start_date + "T00:00:00");
          rangeEndDate.setDate(rangeEndDate.getDate() + Number(horizonDays || 7));
          const rangeEnd = SchedulePage.formatDateLocalYMD(rangeEndDate);
          state.calendar.setOption("visibleRange", { start: rangeStart, end: rangeEnd });
          state.calendar.changeView("dayGridWeek", rangeStart);
        } catch (e) {
          console.error("Failed to restore calendar visibleRange", e);
        }
        SchedulePage.applyCalendarResourceFilter();
      }
      SchedulePage.updateTradeViews();
    }

    // Unscheduled column filters
    [
      "unsched-filter-date",
      "unsched-filter-id",
      "unsched-filter-description",
      "unsched-filter-type",
      "unsched-filter-people",
      "unsched-filter-priority",
      "unsched-filter-duration",
      "unsched-filter-trade",
    ].forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("input", () => {
          SchedulePage.updateTradeViews();
        });
      }
    });
  }

  window.initSchedulePage = initSchedulePage;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSchedulePage);
  } else {
    initSchedulePage();
  }
})();
