(function () {
  // ---------------------------------------------------------------------------
  // Shared state
  // ---------------------------------------------------------------------------
  let calendar;
  let latestSchedule = null;
  let latestWorkOrders = [];
  let scheduledSort = { key: "date", dir: "asc" };
  let unscheduledSort = { key: "date", dir: "asc" };
  let manualScheduledIds = new Set();
  let manualUnscheduledIds = new Set();
  let dragWoId = null;
  let allCalendarEvents = [];
  let currentCalendarEvents = [];
  let manualScheduleOverrides = {};

  // ---------------------------------------------------------------------------
  // Date & formatting utilities
  // ---------------------------------------------------------------------------
  function formatDateLocalYMD(d) {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  // ---------------------------------------------------------------------------
  // Calendar / man-hours logic
  // ---------------------------------------------------------------------------
  function getManHoursForDate(dateStr) {
    if (!dateStr || !latestWorkOrders.length) return 0;
    const woById = new Map(latestWorkOrders.map((wo) => [String(wo.id), wo]));
    let total = 0;
    for (const ev of currentCalendarEvents) {
      let evDate = "";
      if (ev.start) {
        if (typeof ev.start === "string") {
          evDate = ev.start.slice(0, 10);
        } else {
          evDate = formatDateLocalYMD(new Date(ev.start));
        }
      }
      if (evDate !== dateStr) continue;
      const woId = ev.extendedProps?.workOrderId || ev.workOrderId;
      const wo = woById.get(String(woId));
      const dur = wo ? Number(wo.duration_hours || 0) : 0;
      const people = wo ? Number(wo.num_people || 1) : 1;
      total += dur * people;
    }
    return total;
  }

  const TRADE_COLORS = [
    "#22c55e",
    "#3b82f6",
    "#a855f7",
    "#ec4899",
    "#f97316",
    "#eab308",
    "#06b6d4",
    "#facc15",
    "#4ade80",
    "#f472b6",
  ];

  // Populated from backend /api/optimize response (data.shift_colors)
  let shiftColors = {};

  function getTradeColor(trade) {
    if (!trade) return "#6b7280";
    const colorFromShift = shiftColors[trade];
    if (colorFromShift) {
      return colorFromShift;
    }
    if (!trade) return "#6b7280";
    let hash = 0;
    const s = String(trade);
    for (let i = 0; i < s.length; i++) {
      hash = (hash * 31 + s.charCodeAt(i)) | 0;
    }
    const idx = Math.abs(hash) % TRADE_COLORS.length;
    return TRADE_COLORS[idx];
  }

  function getTypeBadgeInfo(type, safety) {
    const t = (type || "").toLowerCase();
    if (safety) {
      return { text: "+", className: "type-safety" };
    }
    if (t.includes("preventive")) {
      return { text: "PM", className: "type-pm" };
    }
    if (t.includes("planned")) {
      return { text: "P", className: "type-p" };
    }
    if (t.includes("process")) {
      return { text: "PI", className: "type-pi" };
    }
    if (t.includes("corrective")) {
      return { text: "C", className: "type-c" };
    }
    if (t.includes("ehs")) {
      return { text: "EHS", className: "type-ehs" };
    }
    return { text: "", className: "" };
  }

  function buildWorkOrderContent(woId, resourceId, equipment, description, type, safety) {
    const maxDescLen = 60;
    const truncatedDesc = (description || "").slice(0, maxDescLen);

    const line1 = `WO ${woId}${resourceId ? " (" + resourceId + ")" : ""}`;
    const line2 = equipment || "";
    const line3 = truncatedDesc;

    const container = document.createElement("div");
    container.className = "wo-event";

    [line1, line2, line3].forEach((text) => {
      if (!text) return;
      const div = document.createElement("div");
      div.textContent = text;
      container.appendChild(div);
    });

    const badgeInfo = getTypeBadgeInfo(type, safety);
    if (badgeInfo.text) {
      const badge = document.createElement("span");
      badge.className = `wo-type-badge ${badgeInfo.className}`;
      badge.textContent = badgeInfo.text;
      container.appendChild(badge);
    }

    return container;
  }

  function initCalendar() {
    const calendarEl = document.getElementById("calendar");
    if (!calendarEl) {
      console.error("Calendar element not found in DOM.");
      return;
    }
    if (typeof FullCalendar === "undefined") {
      console.error("FullCalendar library is not loaded. Skipping calendar init.");
      return;
    }
    calendar = new FullCalendar.Calendar(calendarEl, {
      initialView: "dayGridWeek",
      height: "auto",
      headerToolbar: {
        left: "prev,next today",
        center: "title",
        right: "dayGridWeek",
      },
      firstDay: 1,
      themeSystem: "standard",
      editable: true,
      droppable: true,
      dayCellDidMount: function (info) {
        const dateStr = formatDateLocalYMD(info.date);
        const manHrs = getManHoursForDate(dateStr);
        let badge = info.el.querySelector(".man-hours-badge");
        if (!badge) {
          badge = document.createElement("div");
          badge.className = "man-hours-badge";
          info.el.appendChild(badge);
        }
        badge.textContent = manHrs > 0 ? manHrs + " man-hrs" : "";
        badge.style.display = manHrs > 0 ? "block" : "none";
      },
      eventContent: function (arg) {
        const ext = arg.event.extendedProps || {};
        const woId = ext.workOrderId || arg.event.title || "";
        const resourceId = ext.resourceId || "";
        const equipment = ext.equipment || "";
        const description = ext.description || "";
        const type = ext.type || "";
        const safety = !!ext.safety;

        const container = buildWorkOrderContent(
          woId,
          resourceId,
          equipment,
          description,
          type,
          safety
        );

        return { domNodes: [container] };
      },
      eventDidMount: function (info) {
        const woId = info.event.extendedProps?.workOrderId;
        if (!woId || !latestWorkOrders.length) return;
        const wo = latestWorkOrders.find((w) => String(w.id) === String(woId));
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
          const key = String(woId);
          manualScheduledIds.delete(key);
          manualUnscheduledIds.add(key);
          delete manualScheduleOverrides[key];
          rebuildAllCalendarEvents();
          applyCalendarResourceFilter();
          updateTradeViews();
        }
      },
      eventDrop: function (info) {
        const woId = info.event.extendedProps?.workOrderId;
        if (!woId || !latestSchedule) return;
        const start = info.event.start;
        if (!start) return;
        const scheduleStart = new Date(latestSchedule.start_date + "T00:00:00");
        const dayOffset = Math.round((start - scheduleStart) / (24 * 60 * 60 * 1000));
        manualScheduleOverrides[woId] = {
          day_offset: dayOffset,
          resource_id: info.event.extendedProps?.resourceId || "",
        };
        rebuildAllCalendarEvents();
        applyCalendarResourceFilter();
        updateTradeViews();
      },
    });
    calendar.render();
    calendarEl.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
    });
    calendarEl.addEventListener("drop", (e) => {
      e.preventDefault();
      const woId =
        e.dataTransfer.getData("application/x-unscheduled-wo") ||
        e.dataTransfer.getData("text/plain") ||
        dragWoId;
      if (!woId || !latestSchedule || !latestWorkOrders.length) return;
      const el = document.elementFromPoint(e.clientX, e.clientY);
      const dayCell = el?.closest?.(".fc-daygrid-day");
      const dateStr = dayCell?.getAttribute?.("data-date");
      if (!dateStr) return;
      const scheduleStart = new Date(latestSchedule.start_date + "T00:00:00");
      const dropDate = new Date(dateStr + "T00:00:00");
      const dayOffset = Math.round((dropDate - scheduleStart) / (24 * 60 * 60 * 1000));
      const wo = latestWorkOrders.find((w) => String(w.id) === String(woId));
      const resourceId = wo ? String(wo.trade || "") : "";
      manualScheduleOverrides[woId] = { day_offset: dayOffset, resource_id: resourceId };
      manualScheduledIds.add(woId);
      manualUnscheduledIds.delete(woId);
      rebuildAllCalendarEvents();
      applyCalendarResourceFilter();
      updateTradeViews();
    });
  }

  function setStatus(message) {
    const el = document.getElementById("status");
    if (el) el.textContent = message || "";
  }

  function populateResourceSelect(schedule, workOrders) {
    const selectEl = document.getElementById("resource-select");
    if (!selectEl) return;
    const resources = new Set();
    (schedule?.assignments || []).forEach((a) => {
      const r = String(a.resource_id || "").trim();
      if (r) resources.add(r);
    });
    (workOrders || []).forEach((wo) => {
      const r = String(wo.trade || "").trim();
      if (r) resources.add(r);
    });
    const sorted = Array.from(resources).sort();
    selectEl.innerHTML = "";
    const allOpt = document.createElement("option");
    allOpt.value = "";
    allOpt.textContent = "All resources";
    selectEl.appendChild(allOpt);
    for (const r of sorted) {
      const opt = document.createElement("option");
      opt.value = r;
      opt.textContent = r;
      selectEl.appendChild(opt);
    }
  }

  function applyCalendarResourceFilter() {
    if (!calendar) return;
    const selectEl = document.getElementById("resource-select");
    const selected = selectEl && selectEl.value ? selectEl.value : "";
    const events = selected
      ? allCalendarEvents.filter((e) => e.resourceId === selected)
      : allCalendarEvents;
    currentCalendarEvents = events;
    calendar.removeAllEvents();
    calendar.addEventSource(events);
    requestAnimationFrame(() => updateAllManHoursBadges());
  }

  function updateAllManHoursBadges() {
    if (!calendar) return;
    const el = calendar.el;
    if (!el) return;
    el.querySelectorAll(".fc-daygrid-day[data-date]").forEach((dayEl) => {
      const dateStr = dayEl.getAttribute("data-date");
      const manHrs = getManHoursForDate(dateStr);
      let badge = dayEl.querySelector(".man-hours-badge");
      if (!badge) {
        badge = document.createElement("div");
        badge.className = "man-hours-badge";
        dayEl.appendChild(badge);
      }
      badge.textContent = manHrs > 0 ? manHrs + " man-hrs" : "";
      badge.style.display = manHrs > 0 ? "block" : "none";
    });
  }

  function rebuildAllCalendarEvents() {
    if (!latestSchedule || !latestSchedule.start_date) return;
    const startDate = new Date(latestSchedule.start_date + "T00:00:00");
    const woById = new Map(latestWorkOrders.map((wo) => [String(wo.id), wo]));
    const used = new Set();
    const events = [];
    for (const woId of Object.keys(manualScheduleOverrides)) {
      if (manualUnscheduledIds.has(String(woId))) continue;
      const override = manualScheduleOverrides[woId];
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
    for (const a of latestSchedule.assignments || []) {
      const woId = String(a.work_order_id);
      if (used.has(woId)) continue;
      if (manualUnscheduledIds.has(woId)) continue;
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
    allCalendarEvents = events;
  }

  // ---------------------------------------------------------------------------
  // Tables / sorting logic
  // ---------------------------------------------------------------------------
  function compareValues(a, b, key, dir) {
    const av = a[key];
    const bv = b[key];
    if (av == null && bv == null) return 0;
    if (av == null) return dir === "asc" ? 1 : -1;
    if (bv == null) return dir === "asc" ? -1 : 1;
    if (key === "date") {
      const ad = new Date(av);
      const bd = new Date(bv);
      if (ad < bd) return dir === "asc" ? -1 : 1;
      if (ad > bd) return dir === "asc" ? 1 : -1;
      return 0;
    }
    if (key === "priority" || key === "duration") {
      const an = Number(av);
      const bn = Number(bv);
      if (an < bn) return dir === "asc" ? -1 : 1;
      if (an > bn) return dir === "asc" ? 1 : -1;
      return 0;
    }
    const as = String(av);
    const bs = String(bv);
    if (as < bs) return dir === "asc" ? -1 : 1;
    if (as > bs) return dir === "asc" ? 1 : -1;
    return 0;
  }

  function updateTradeViews() {
    const scheduledBody = document.getElementById("scheduled-tbody");
    const unscheduledBody = document.getElementById("unscheduled-tbody");
    if (!unscheduledBody) return;

    if (scheduledBody) {
      scheduledBody.innerHTML = "";
    }
    unscheduledBody.innerHTML = "";

    if (!latestSchedule || !latestWorkOrders.length) {
      return;
    }

    const selectEl = document.getElementById("resource-select");
    const selectedResource = selectEl ? selectEl.value : "";

    const woById = new Map(latestWorkOrders.map((wo) => [String(wo.id), wo]));

    const assignments = latestSchedule.assignments || [];
    const assignedById = new Map();
    for (const a of assignments) {
      assignedById.set(String(a.work_order_id), a);
    }

    const rowsScheduled = [];
    const rowsUnscheduled = [];

    const scheduleStart = latestSchedule.start_date
      ? new Date(latestSchedule.start_date + "T00:00:00")
      : null;

    for (const wo of latestWorkOrders) {
      const key = String(wo.id);
      const forcedUnscheduled = manualUnscheduledIds.has(key);
      const forcedScheduled = manualScheduledIds.has(key);
      const assigned = assignedById.get(key);

      if (!forcedUnscheduled && (assigned || forcedScheduled) && scheduleStart) {
        const override = manualScheduleOverrides[key];
        const dayOffset =
          override != null
            ? Number(override.day_offset ?? 0)
            : assigned
            ? Number(assigned.day_offset || 0)
            : 0;
        const resourceId =
          override != null
            ? override.resource_id || wo.trade
            : assigned
            ? assigned.resource_id
            : wo.trade;
        const assignedDate = new Date(scheduleStart);
        assignedDate.setDate(scheduleStart.getDate() + dayOffset);
        rowsScheduled.push({
          date: formatDateLocalYMD(assignedDate),
          id: wo.id,
          description: wo.description,
          priority: wo.priority,
          duration: wo.duration_hours,
          trade: wo.trade,
          resource: resourceId,
        });
      } else if (!forcedScheduled) {
        rowsUnscheduled.push({
          date: wo.schedule_date || null,
          id: wo.id,
          description: wo.description,
          priority: wo.priority,
          duration: wo.duration_hours,
          trade: wo.trade,
        });
      }
    }

    rowsScheduled.sort((a, b) =>
      compareValues(a, b, scheduledSort.key, scheduledSort.dir)
    );
    rowsUnscheduled.sort((a, b) =>
      compareValues(a, b, unscheduledSort.key, unscheduledSort.dir)
    );

    const scheduledFiltered = selectedResource
      ? rowsScheduled.filter((row) => String(row.resource || "") === selectedResource)
      : rowsScheduled;
    const unscheduledFiltered = selectedResource
      ? rowsUnscheduled.filter((row) => String(row.trade || "") === selectedResource)
      : rowsUnscheduled;

    if (scheduledBody) {
      for (const row of scheduledFiltered) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${row.date || ""}</td>
            <td>${row.id}</td>
            <td>${row.description}</td>
            <td>${row.priority}</td>
            <td>${row.duration}</td>
            <td>${row.trade}</td>
            <td>${row.resource || ""}</td>`;
        tr.draggable = true;
        tr.dataset.woId = String(row.id);
        tr.dataset.table = "scheduled";
        scheduledBody.appendChild(tr);
      }
    }

    for (const row of unscheduledFiltered) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${row.date != null ? row.date : ""}</td>
          <td>${row.id}</td>
          <td>${row.description ?? ""}</td>
          <td>${row.priority}</td>
          <td>${row.duration}</td>
          <td>${row.trade ?? ""}</td>`;
      tr.draggable = true;
      tr.dataset.woId = String(row.id);
      tr.dataset.table = "unscheduled";
      unscheduledBody.appendChild(tr);
    }

    // Attach drag handlers for rows
    if (scheduledBody) {
      scheduledBody.querySelectorAll("tr").forEach((tr) => {
        tr.addEventListener("dragstart", (e) => {
          dragWoId = tr.dataset.woId;
          e.dataTransfer.effectAllowed = "move";
          e.dataTransfer.setData("text/plain", dragWoId);
        });
      });
    }
    unscheduledBody.querySelectorAll("tr").forEach((tr) => {
      tr.addEventListener("dragstart", (e) => {
        dragWoId = tr.dataset.woId;
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", dragWoId);
        e.dataTransfer.setData("application/x-unscheduled-wo", dragWoId);

        // Create a drag image that looks like a calendar event for this work order
        const id = tr.dataset.woId;
        const wo = latestWorkOrders.find((w) => String(w.id) === String(id));
        if (!wo || !e.dataTransfer) return;
        const resourceId = String(wo.trade || "");
        const color = getTradeColor(resourceId);

        const dragEl = document.createElement("div");
        dragEl.className =
          "fc-daygrid-event fc-daygrid-block-event fc-h-event fc-event";
        dragEl.style.backgroundColor = color;
        dragEl.style.borderColor = color;
        dragEl.style.position = "absolute";
        dragEl.style.top = "-1000px"; // off-screen
        dragEl.style.left = "-1000px";

        const inner = buildWorkOrderContent(
          wo.id,
          resourceId,
          wo.equipment || "",
          wo.description || "",
          wo.type || "",
          !!wo.safety
        );

        dragEl.appendChild(inner);
        document.body.appendChild(dragEl);

        const rect = dragEl.getBoundingClientRect();
        const offsetX = rect.width / 2;
        const offsetY = rect.height / 2;
        e.dataTransfer.setDragImage(dragEl, offsetX, offsetY);

        // Clean up after the current event loop tick
        setTimeout(() => {
          document.body.removeChild(dragEl);
        }, 0);
      });
    });
  }

  // ---------------------------------------------------------------------------
  // API / event handlers
  // ---------------------------------------------------------------------------
  async function postOptimize(formData) {
    const response = await fetch("/api/optimize", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error("Optimization failed");
    }
    return response.json();
  }

  function initFormHandlers() {
    const form = document.getElementById("optimize-form");
    if (form) {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const fileInput = document.getElementById("backlog");
        if (!fileInput || !fileInput.files.length) {
          alert("Please choose a backlog .xlsx file.");
          return;
        }
        const fd = new FormData();
        fd.append("backlog_file", fileInput.files[0]);

        try {
          setStatus("Optimizing schedule...");
          const data = await postOptimize(fd);
          console.log("optimize response", data);
          console.log(
            "schedule assignments length",
            data?.schedule?.assignments?.length || 0
          );
          console.log("work_orders length", (data.work_orders || []).length);
          console.log(
            "trades",
            Array.from(
              new Set(
                (data.work_orders || []).map((wo) =>
                  String(wo.trade || "").trim()
                )
              )
            )
          );
          // Update global state from response
          latestSchedule = data.schedule || null;
          latestWorkOrders = data.work_orders || [];
          shiftColors = data.shift_colors || {};
          manualScheduleOverrides = {};
          populateResourceSelect(latestSchedule, latestWorkOrders);

          rebuildAllCalendarEvents();

          if (!calendar) {
            console.error("Calendar not initialized; initializing now.");
            initCalendar();
          }
          if (calendar) {
            try {
              const horizonDays = data.schedule.horizon_days || 7;
              const rangeStart = data.schedule.start_date;
              const rangeEndDate = new Date(
                data.schedule.start_date + "T00:00:00"
              );
              rangeEndDate.setDate(
                rangeEndDate.getDate() + Number(horizonDays || 7)
              );
              const rangeEnd = formatDateLocalYMD(rangeEndDate);
              calendar.setOption("visibleRange", {
                start: rangeStart,
                end: rangeEnd,
              });
              calendar.changeView("dayGridWeek", rangeStart);
            } catch (e) {
              console.error("Failed to set calendar visibleRange", e);
            }
            applyCalendarResourceFilter();
          } else {
            console.error("Calendar is still undefined after initCalendar().");
          }
          setStatus(
            `Scheduled ${allCalendarEvents.length} assignments over 7 days starting ${data.schedule.start_date}.`
          );
          updateTradeViews();
        } catch (err) {
          console.error(err);
          setStatus("Error during optimization. See console for details.");
        }
      });
    }

    const downloadBtn = document.getElementById("download-xlsx-btn");
    if (downloadBtn) {
      downloadBtn.addEventListener("click", async () => {
        const fileInput = document.getElementById("backlog");
        if (!fileInput || !fileInput.files.length) {
          alert("Please choose a backlog .xlsx file first.");
          return;
        }
        const fd = new FormData();
        fd.append("backlog_file", fileInput.files[0]);
        try {
          setStatus("Generating schedule .xlsx...");
          const response = await fetch("/api/optimize/xlsx", {
            method: "POST",
            body: fd,
          });
          if (!response.ok) {
            throw new Error("Failed to generate .xlsx");
          }
          const blob = await response.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "schedule.xlsx";
          document.body.appendChild(a);
          a.click();
          a.remove();
          window.URL.revokeObjectURL(url);
          setStatus("Downloaded schedule.xlsx.");
        } catch (err) {
          console.error(err);
          setStatus("Error generating .xlsx. See console for details.");
        }
      });
    }
  }

  function initResourceFilter() {
    const select = document.getElementById("resource-select");
    if (select) {
      select.addEventListener("change", () => {
        updateTradeViews();
        applyCalendarResourceFilter();
      });
    }
  }

  function initSorting() {
    document
      .querySelectorAll("th[data-table='scheduled']")
      .forEach((th) => {
        th.addEventListener("click", () => {
          const key = th.getAttribute("data-key");
          if (!key) return;
          if (scheduledSort.key === key) {
            scheduledSort.dir = scheduledSort.dir === "asc" ? "desc" : "asc";
          } else {
            scheduledSort.key = key;
            scheduledSort.dir = "asc";
          }
          updateTradeViews();
        });
      });

    document
      .querySelectorAll("th[data-table='unscheduled']")
      .forEach((th) => {
        th.addEventListener("click", () => {
          const key = th.getAttribute("data-key");
          if (!key) return;
          if (unscheduledSort.key === key) {
            unscheduledSort.dir =
              unscheduledSort.dir === "asc" ? "desc" : "asc";
          } else {
            unscheduledSort.key = key;
            unscheduledSort.dir = "asc";
          }
          updateTradeViews();
        });
      });
  }

  function initDragDrop() {
    const scheduledBody = document.getElementById("scheduled-tbody");
    const unscheduledBody = document.getElementById("unscheduled-tbody");

    function handleDropToScheduled(e) {
      e.preventDefault();
      try {
        const id = e.dataTransfer.getData("text/plain") || dragWoId;
        if (!id) return;
        manualUnscheduledIds.delete(id);
        manualScheduledIds.add(id);
        updateTradeViews();
      } catch (err) {
        console.error("handleDropToScheduled", err);
      }
    }

    function handleDropToUnscheduled(e) {
      e.preventDefault();
      try {
        const id = e.dataTransfer.getData("text/plain") || dragWoId;
        if (!id) return;
        manualScheduledIds.delete(id);
        manualUnscheduledIds.add(id);
        rebuildAllCalendarEvents();
        applyCalendarResourceFilter();
        updateTradeViews();
      } catch (err) {
        console.error("handleDropToUnscheduled", err);
      }
    }

    if (scheduledBody) {
      scheduledBody.addEventListener("dragover", (e) => e.preventDefault());
      scheduledBody.addEventListener("drop", handleDropToScheduled);
    }
    if (unscheduledBody) {
      unscheduledBody.addEventListener("dragover", (e) => e.preventDefault());
      unscheduledBody.addEventListener("drop", handleDropToUnscheduled);
    }
  }

  // ---------------------------------------------------------------------------
  // Public entry point
  // ---------------------------------------------------------------------------
  function initSchedulePage() {
    initCalendar();
    initFormHandlers();
    initResourceFilter();
    initSorting();
    initDragDrop();
  }

  // Expose for potential future use
  window.initSchedulePage = initSchedulePage;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initSchedulePage);
  } else {
    initSchedulePage();
  }
})();

