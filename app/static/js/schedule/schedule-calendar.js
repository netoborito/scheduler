/**
 * FullCalendar setup, events, man-hours badges. Depends: schedule-state, schedule-utils, schedule-shifts.
 */
(function () {
  "use strict";
  const SchedulePage = window.SchedulePage;
  const state = SchedulePage.state;
  const formatDateLocalYMD = SchedulePage.formatDateLocalYMD;
  const getManHoursForDate = SchedulePage.getManHoursForDate;
  const getAvailableManHoursForDate = SchedulePage.getAvailableManHoursForDate;
  const getTradeColor = SchedulePage.getTradeColor;
  const buildWorkOrderContent = SchedulePage.buildWorkOrderContent;

  // ── Edit Modal helpers ──────────────────────────────────────────────
  // Double-click detection state: track the last-clicked WO and timestamp
  // so we can distinguish single clicks (drag) from double clicks (edit).
  let lastClickWoId = null;
  let lastClickTime = 0;

  /** Show the edit modal, pre-filled with the WO's current values. */
  function openEditModal(woId, currentDateStr, currentTrade) {
    const overlay = document.getElementById("wo-edit-modal");
    if (!overlay) return;

    // Look up full WO data for read-only fields
    const wo = state.latestWorkOrders.find((w) => String(w.id) === String(woId));

    // Fill read-only fields
    document.getElementById("wo-edit-id").textContent = woId;
    document.getElementById("wo-edit-desc").textContent = wo ? wo.description || "" : "";
    document.getElementById("wo-edit-priority").textContent = wo ? (wo.priority ?? "") : "";
    document.getElementById("wo-edit-duration").textContent = wo ? (wo.duration_hours ?? 0) : "";
    document.getElementById("wo-edit-people").textContent = wo ? (wo.num_people ?? 1) : "";

    // Set editable date field (YYYY-MM-DD string for <input type="date">)
    document.getElementById("wo-edit-date").value = currentDateStr || "";

    // Build trade dropdown from the shifts already loaded in state
    const tradeSelect = document.getElementById("wo-edit-trade");
    tradeSelect.innerHTML = "";
    const trades = (state.shiftAvailability || []).map((s) => s.trade).filter(Boolean);
    for (const t of trades) {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      if (t === currentTrade) opt.selected = true;
      tradeSelect.appendChild(opt);
    }

    // Stash the WO id so saveEditModal knows which WO to update
    overlay.dataset.woId = woId;

    overlay.classList.add("visible");
  }

  /** Hide the edit modal. */
  function closeEditModal() {
    const overlay = document.getElementById("wo-edit-modal");
    if (overlay) overlay.classList.remove("visible");
  }

  /**
   * Read the user's edits from the modal, write them as an override,
   * then refresh the calendar. Same flow as eventDrop.
   */
  function saveEditModal() {
    const overlay = document.getElementById("wo-edit-modal");
    if (!overlay || !state.latestSchedule) return;

    const woId = overlay.dataset.woId;
    if (!woId) return;

    // Read new values from inputs
    const newDateStr = document.getElementById("wo-edit-date").value;
    const newTrade = document.getElementById("wo-edit-trade").value;
    if (!newDateStr) return;

    const scheduleStart = new Date(state.latestSchedule.start_date + "T00:00:00");
    const newDate = new Date(newDateStr + "T00:00:00");
    const dayOffset = Math.round((newDate - scheduleStart) / (24 * 60 * 60 * 1000));

    placeWorkOrder(woId, dayOffset, newTrade);
    closeEditModal();
  }

  // Wire up Save / Cancel buttons + click-outside-to-close
  document.addEventListener("DOMContentLoaded", function () {
    var saveBtn = document.getElementById("wo-edit-save");
    if (saveBtn) saveBtn.addEventListener("click", saveEditModal);

    var cancelBtn = document.getElementById("wo-edit-cancel");
    if (cancelBtn) cancelBtn.addEventListener("click", closeEditModal);

    // Clicking the dark backdrop (not the card) also closes
    var overlay = document.getElementById("wo-edit-modal");
    if (overlay) {
      overlay.addEventListener("click", function (e) {
        if (e.target === overlay) closeEditModal();
      });
    }
  });

  // ── End Edit Modal helpers ──────────────────────────────────────────

  // ── Shared placement helpers ──────────────────────────────────────

  /** Apply a placement override (state only, no DOM rebuild). */
  function applyPlacement(woId, dayOffset, resourceId) {
    var key = String(woId);
    state.manualScheduleOverrides[key] = {
      day_offset: dayOffset,
      resource_id: resourceId,
    };
    state.manualScheduledIds.add(key);
    state.manualUnscheduledIds.delete(key);
  }

  /** Rebuild calendar, tables, and persist after state mutations. */
  function refreshCalendar() {
    rebuildAllCalendarEvents();
    applyCalendarResourceFilter();
    SchedulePage.updateTradeViews();
    if (SchedulePage.persistScheduleState) {
      SchedulePage.persistScheduleState();
    }
  }

  /** Place a single WO on the calendar and refresh. */
  function placeWorkOrder(woId, dayOffset, resourceId) {
    applyPlacement(woId, dayOffset, resourceId);
    refreshCalendar();
  }

  /** Remove a WO from the calendar and refresh. */
  function unscheduleWorkOrder(woId) {
    var key = String(woId);
    state.manualScheduledIds.delete(key);
    state.manualUnscheduledIds.add(key);
    delete state.manualScheduleOverrides[key];
    refreshCalendar();
  }

  // ── End Shared placement helpers ──────────────────────────────────

  function updateAllManHoursBadges() {
    if (!state.calendar) return;
    const el = state.calendar.el;
    if (!el) return;
    el.querySelectorAll(".fc-daygrid-day[data-date]").forEach((dayEl) => {
      const dateStr = dayEl.getAttribute("data-date");
      const scheduled = getManHoursForDate(dateStr);
      const available = getAvailableManHoursForDate(dateStr);
      let badge = dayEl.querySelector(".man-hours-badge");
      if (!badge) {
        badge = document.createElement("div");
        badge.className = "man-hours-badge";
        dayEl.appendChild(badge);
      }
      if (available != null) {
        badge.textContent = scheduled + "/" + available;
        badge.style.display = "block";
        badge.classList.toggle("man-hours-over", scheduled > available);
      } else {
        badge.textContent = scheduled > 0 ? scheduled + " man-hrs" : "";
        badge.style.display = scheduled > 0 ? "block" : "none";
        badge.classList.remove("man-hours-over");
      }
    });
  }

  function rebuildAllCalendarEvents() {
    if (!state.latestSchedule || !state.latestSchedule.start_date) return;
    const startDate = new Date(state.latestSchedule.start_date + "T00:00:00");
    const woById = new Map(state.latestWorkOrders.map((wo) => [String(wo.id), wo]));
    const used = new Set();
    const events = [];
    for (const woId of Object.keys(state.manualScheduleOverrides)) {
      if (state.manualUnscheduledIds.has(String(woId))) continue;
      const override = state.manualScheduleOverrides[woId];
      const wo = woById.get(woId);
      const eventDate = new Date(startDate);
      eventDate.setDate(startDate.getDate() + (override.day_offset || 0));
      const dateStr = formatDateLocalYMD(eventDate);
      const resourceId = override.resource_id || (wo ? String(wo.trade) : "");
      events.push({
        title: `${woId} (${resourceId})`,
        start: dateStr,
        allDay: true,
        backgroundColor: getTradeColor(resourceId),
        borderColor: getTradeColor(resourceId),
        resourceId: resourceId,
        extendedProps: {
          workOrderId: woId,
          resourceId: resourceId,
          equipment: wo ? wo.equipment || "" : "",
          description: wo ? wo.description || "" : "",
          type: wo ? wo.type || "" : "",
          safety: wo ? !!wo.safety : false,
        },
      });
      used.add(woId);
    }
    for (const a of state.latestSchedule.assignments || []) {
      const woId = String(a.work_order_id);
      if (used.has(woId) || state.manualUnscheduledIds.has(woId)) continue;
      const eventDate = new Date(startDate);
      eventDate.setDate(startDate.getDate() + Number(a.day_offset || 0));
      const dateStr = formatDateLocalYMD(eventDate);
      const resourceId = a.resource_id;
      const wo = woById.get(woId);
      events.push({
        title: `${woId} (${resourceId})`,
        start: dateStr,
        allDay: true,
        backgroundColor: getTradeColor(resourceId),
        borderColor: getTradeColor(resourceId),
        resourceId: resourceId,
        extendedProps: {
          workOrderId: woId,
          resourceId: resourceId,
          equipment: wo ? wo.equipment || "" : "",
          description: wo ? wo.description || "" : "",
          type: wo ? wo.type || "" : "",
          safety: wo ? !!wo.safety : false,
        },
      });
    }
    state.allCalendarEvents = events;
  }

  function applyCalendarResourceFilter() {
    if (!state.calendar) return;
    const selectEl = document.getElementById("resource-select");
    const selected = selectEl && selectEl.value ? selectEl.value : "";
    state.currentCalendarEvents = selected
      ? state.allCalendarEvents.filter((e) => e.resourceId === selected)
      : state.allCalendarEvents;
    state.calendar.removeAllEvents();
    state.calendar.addEventSource(state.currentCalendarEvents);
    requestAnimationFrame(updateAllManHoursBadges);
  }

  function initCalendar() {
    const calendarEl = document.getElementById("calendar");
    if (!calendarEl) {
      console.error("Calendar element not found in DOM.");
      return;
    }
    if (typeof FullCalendar === "undefined") {
      console.error("FullCalendar library is not loaded.");
      return;
    }
    const defaultStart = calendarEl.dataset.defaultStart || undefined;
    let calendarStart = defaultStart;
    if (defaultStart) {
      const d = new Date(defaultStart + "T00:00:00");
      d.setDate(d.getDate() - 7);
      calendarStart = d.toISOString().slice(0, 10);
    }
    const calendar = new FullCalendar.Calendar(calendarEl, {
      initialView: "twoWeek",
      views: { twoWeek: { type: "dayGrid", duration: { days: 14 } } },
      height: "auto",
      initialDate: calendarStart,
      headerToolbar: { left: "prev,next today", center: "title", right: "" },
      firstDay: 1,
      themeSystem: "standard",
      editable: true,
      droppable: true,
      dayCellDidMount: function (info) {
        const dateStr = formatDateLocalYMD(info.date);
        const scheduled = getManHoursForDate(dateStr);
        const available = getAvailableManHoursForDate(dateStr);
        let badge = info.el.querySelector(".man-hours-badge");
        if (!badge) {
          badge = document.createElement("div");
          badge.className = "man-hours-badge";
          info.el.appendChild(badge);
        }
        if (available != null) {
          badge.textContent = scheduled + "/" + available;
          badge.style.display = "block";
          badge.classList.toggle("man-hours-over", scheduled > available);
        } else {
          badge.textContent = scheduled > 0 ? scheduled + " man-hrs" : "";
          badge.style.display = scheduled > 0 ? "block" : "none";
          badge.classList.remove("man-hours-over");
        }
      },
      eventContent: function (arg) {
        const ext = arg.event.extendedProps || {};
        const container = buildWorkOrderContent(
          ext.workOrderId || arg.event.title || "",
          ext.resourceId || "",
          ext.equipment || "",
          ext.description || "",
          ext.type || "",
          !!ext.safety
        );
        return { domNodes: [container] };
      },
      eventDragStart: function () {
        state.dragSource = "calendar";
      },
      eventDidMount: function (info) {
        const woId = info.event.extendedProps?.workOrderId;
        if (!woId || !state.latestWorkOrders.length) return;
        const wo = state.latestWorkOrders.find((w) => String(w.id) === String(woId));
        if (!wo) return;
        const lines = [
          "WO " + woId,
          wo.description ? "Description: " + wo.description : "",
          "Priority: " + (wo.priority ?? ""),
          "Duration: " + (wo.duration_hours ?? 0) + " h",
          "People: " + (wo.num_people ?? 1),
          "Trade: " + (wo.trade ?? ""),
        ].filter(Boolean);
        info.el.title = lines.join("\n");
      },
      eventDragStop: function (info) {
        const jsEvent = info.jsEvent;
        if (!jsEvent) return;
        const unscheduledBody = document.getElementById("unscheduled-tbody");
        if (!unscheduledBody) return;
        const rect = unscheduledBody.getBoundingClientRect();
        const x = jsEvent.clientX;
        const y = jsEvent.clientY;
        if (x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) {
          const woId = info.event.extendedProps?.workOrderId;
          if (!woId) return;
          unscheduleWorkOrder(woId);
        }
      },
      eventDrop: function (info) {
        const woId = info.event.extendedProps?.workOrderId;
        if (!woId || !state.latestSchedule) return;
        const start = info.event.start;
        if (!start) return;
        const scheduleStart = new Date(state.latestSchedule.start_date + "T00:00:00");
        const dayOffset = Math.round((start - scheduleStart) / (24 * 60 * 60 * 1000));
        placeWorkOrder(woId, dayOffset, info.event.extendedProps?.resourceId || "");
      },
      // Double-click to open the edit modal.
      // Two clicks on the same WO within 350ms = double-click.
      eventClick: function (info) {
        const woId = info.event.extendedProps?.workOrderId;
        if (!woId) return;
        const now = Date.now();
        if (lastClickWoId === woId && now - lastClickTime < 350) {
          // Double-click detected -- open the edit modal
          lastClickWoId = null;
          const dateStr = info.event.startStr || "";
          const trade = info.event.extendedProps?.resourceId || "";
          openEditModal(woId, dateStr, trade);
        } else {
          // First click -- just record it and wait for possible second
          lastClickWoId = woId;
          lastClickTime = now;
        }
      },
    });
    calendar.render();
    state.calendar = calendar;

    function syncRibbonTitle() {
      var titleEl = document.getElementById("cal-title");
      if (!titleEl) return;
      var title = calendar.view.title;
      if (!title) {
        var start = calendar.view.activeStart;
        var end = calendar.view.activeEnd;
        if (start && end) {
          var endDisplay = new Date(end);
          endDisplay.setDate(endDisplay.getDate() - 1);
          title = start.toLocaleDateString(undefined, { month: "short", day: "numeric" })
            + " – " + endDisplay.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
        }
      }
      titleEl.textContent = title || "";
    }
    syncRibbonTitle();
    calendar.on("datesSet", syncRibbonTitle);
    var prevBtn = document.getElementById("cal-prev");
    var nextBtn = document.getElementById("cal-next");
    var todayBtn = document.getElementById("cal-today");
    if (prevBtn) prevBtn.addEventListener("click", function () { calendar.prev(); });
    if (nextBtn) nextBtn.addEventListener("click", function () { calendar.next(); });
    if (todayBtn) todayBtn.addEventListener("click", function () { calendar.today(); });

    calendarEl.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
    });
    calendarEl.addEventListener("drop", (e) => {
      e.preventDefault();
      const woId =
        e.dataTransfer.getData("application/x-unscheduled-wo") ||
        e.dataTransfer.getData("text/plain") ||
        state.dragWoId;
      if (!woId || !state.latestSchedule || !state.latestWorkOrders.length) return;
      const el = document.elementFromPoint(e.clientX, e.clientY);
      const dayCell = el?.closest?.(".fc-daygrid-day");
      const dateStr = dayCell?.getAttribute?.("data-date");
      if (!dateStr) return;
      const scheduleStart = new Date(state.latestSchedule.start_date + "T00:00:00");
      const dropDate = new Date(dateStr + "T00:00:00");
      const dayOffset = Math.round((dropDate - scheduleStart) / (24 * 60 * 60 * 1000));
      const wo = state.latestWorkOrders.find((w) => String(w.id) === String(woId));
      const resourceId = wo ? String(wo.trade || "") : "";
      placeWorkOrder(woId, dayOffset, resourceId);
    });
  }

  SchedulePage.applyPlacement = applyPlacement;
  SchedulePage.refreshCalendar = refreshCalendar;
  SchedulePage.placeWorkOrder = placeWorkOrder;
  SchedulePage.unscheduleWorkOrder = unscheduleWorkOrder;
  SchedulePage.updateAllManHoursBadges = updateAllManHoursBadges;
  SchedulePage.rebuildAllCalendarEvents = rebuildAllCalendarEvents;
  SchedulePage.applyCalendarResourceFilter = applyCalendarResourceFilter;
  SchedulePage.initCalendar = initCalendar;
})();
