/**
 * Resource select, scheduled/unscheduled tables, row drag handlers. Depends: schedule-state, schedule-utils, schedule-shifts, schedule-calendar.
 */
(function () {
  "use strict";
  const SchedulePage = window.SchedulePage;
  const state = SchedulePage.state;
  const formatDateLocalYMD = SchedulePage.formatDateLocalYMD;
  const formatDateDisplay = SchedulePage.formatDateDisplay;
  const compareValues = SchedulePage.compareValues;
  const getTradeColor = SchedulePage.getTradeColor;
  const buildWorkOrderContent = SchedulePage.buildWorkOrderContent;

  function populateResourceSelect(shiftAvailability) {
    const selectEl = document.getElementById("resource-select");
    if (!selectEl) return;
    const trades = new Set();
    (shiftAvailability || []).forEach((s) => {
      const t = String(s.trade || "").trim();
      if (t) trades.add(t);
    });
    const sorted = Array.from(trades).sort();
    selectEl.innerHTML = "";
    const allOpt = document.createElement("option");
    allOpt.value = "";
    allOpt.textContent = "All resources";
    selectEl.appendChild(allOpt);
    for (const t of sorted) {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      selectEl.appendChild(opt);
    }
  }

  function updateTradeViews() {
    const scheduledBody = document.getElementById("scheduled-tbody");
    const unscheduledBody = document.getElementById("unscheduled-tbody");
    if (!unscheduledBody) return;

    if (scheduledBody) scheduledBody.innerHTML = "";
    unscheduledBody.innerHTML = "";

    if (!state.latestWorkOrders.length) return;

    const selectEl = document.getElementById("resource-select");
    const selectedResource = selectEl ? selectEl.value : "";
    const woById = new Map(state.latestWorkOrders.map((wo) => [String(wo.id), wo]));
    const assignments = state.latestSchedule.assignments || [];
    const assignedById = new Map();
    for (const a of assignments) assignedById.set(String(a.work_order_id), a);

    const rowsScheduled = [];
    const rowsUnscheduled = [];
    const scheduleStart = state.latestSchedule.start_date
      ? new Date(state.latestSchedule.start_date + "T00:00:00")
      : null;

    for (const wo of state.latestWorkOrders) {
      const key = String(wo.id);
      const forcedUnscheduled = state.manualUnscheduledIds.has(key);
      const forcedScheduled = state.manualScheduledIds.has(key);
      const assigned = assignedById.get(key);

      if (!forcedUnscheduled && (assigned || forcedScheduled) && scheduleStart) {
        const override = state.manualScheduleOverrides[key];
        const dayOffset =
          override != null ? Number(override.day_offset ?? 0) : assigned ? Number(assigned.day_offset || 0) : 0;
        const resourceId =
          override != null ? override.resource_id || wo.trade : assigned ? assigned.resource_id : wo.trade;
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
          type: wo.type,
          equipment: wo.equipment,
          people: typeof wo.num_people === "number" ? wo.num_people : 1,
          trade: wo.trade,
        });
      }
    }

    rowsScheduled.sort((a, b) => compareValues(a, b, state.scheduledSort.key, state.scheduledSort.dir));
    rowsUnscheduled.sort((a, b) => compareValues(a, b, state.unscheduledSort.key, state.unscheduledSort.dir));

    const scheduledFiltered = selectedResource
      ? rowsScheduled.filter((row) => String(row.resource || "") === selectedResource)
      : rowsScheduled;

    // Column-specific filters for unscheduled list
    const dateFilterEl = document.getElementById("unsched-filter-date");
    const idFilterEl = document.getElementById("unsched-filter-id");
    const descFilterEl = document.getElementById("unsched-filter-description");
    const typeFilterEl = document.getElementById("unsched-filter-type");
    const peopleFilterEl = document.getElementById("unsched-filter-people");
    const prioFilterEl = document.getElementById("unsched-filter-priority");
    const durFilterEl = document.getElementById("unsched-filter-duration");
    const tradeFilterEl = document.getElementById("unsched-filter-trade");

    const dateQuery = dateFilterEl ? dateFilterEl.value.trim().toLowerCase() : "";
    const idQuery = idFilterEl ? idFilterEl.value.trim().toLowerCase() : "";
    const descQuery = descFilterEl ? descFilterEl.value.trim().toLowerCase() : "";
    const typeQuery = typeFilterEl ? typeFilterEl.value.trim().toLowerCase() : "";
    const peopleQuery = peopleFilterEl ? peopleFilterEl.value.trim().toLowerCase() : "";
    const prioQuery = prioFilterEl ? prioFilterEl.value.trim().toLowerCase() : "";
    const durQuery = durFilterEl ? durFilterEl.value.trim().toLowerCase() : "";
    const tradeQuery = tradeFilterEl ? tradeFilterEl.value.trim().toLowerCase() : "";

    const baseUnscheduled = selectedResource
      ? rowsUnscheduled.filter((row) => String(row.trade || "") === selectedResource)
      : rowsUnscheduled;

    const unscheduledFiltered = baseUnscheduled.filter((row) => {
      if (dateQuery) {
        const d = row.date != null ? formatDateDisplay(row.date).toLowerCase() : "";
        if (!d.includes(dateQuery)) return false;
      }
      if (idQuery) {
        const idStr = String(row.id ?? "").toLowerCase();
        if (!idStr.includes(idQuery)) return false;
      }
      if (descQuery) {
        const descStr = String(row.description ?? "").toLowerCase();
        if (!descStr.includes(descQuery)) return false;
      }
      if (typeQuery) {
        const typeStr = String(row.type ?? "").toLowerCase();
        if (!typeStr.includes(typeQuery)) return false;
      }
      if (peopleQuery) {
        const peopleStr = String(row.people ?? "").toLowerCase();
        if (!peopleStr.includes(peopleQuery)) return false;
      }
      if (prioQuery) {
        const prStr = row.priority != null ? String(row.priority).toLowerCase() : "";
        if (!prStr.includes(prioQuery)) return false;
      }
      if (durQuery) {
        const durStr = row.duration != null ? String(row.duration).toLowerCase() : "";
        if (!durStr.includes(durQuery)) return false;
      }
      if (tradeQuery) {
        const tradeStr = String(row.trade ?? "").toLowerCase();
        if (!tradeStr.includes(tradeQuery)) return false;
      }
      return true;
    });

    if (scheduledBody) {
      for (const row of scheduledFiltered) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${row.date || ""}</td><td>${row.id}</td><td>${row.description}</td><td>${row.priority}</td><td>${row.duration}</td><td>${row.trade}</td><td>${row.resource || ""}</td>`;
        tr.draggable = true;
        tr.dataset.woId = String(row.id);
        tr.dataset.table = "scheduled";
        scheduledBody.appendChild(tr);
      }
    }

    for (const row of unscheduledFiltered) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${row.date != null ? formatDateDisplay(row.date) : ""}</td><td>${row.id}</td><td>${row.description ?? ""}</td><td>${row.type ?? ""}</td><td>${row.people ?? ""}</td><td>${row.priority}</td><td>${row.duration}</td><td>${row.trade ?? ""}</td>`;
      tr.draggable = true;
      tr.dataset.woId = String(row.id);
      tr.dataset.table = "unscheduled";
      unscheduledBody.appendChild(tr);
    }

    if (scheduledBody) {
      scheduledBody.querySelectorAll("tr").forEach((tr) => {
        tr.addEventListener("dragstart", (e) => {
          state.dragWoId = tr.dataset.woId;
          state.dragSource = "scheduled";
          if (e.dataTransfer) {
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData("text/plain", state.dragWoId);
          }
        });
      });
    }
    unscheduledBody.querySelectorAll("tr").forEach((tr) => {
      tr.addEventListener("dragstart", (e) => {
        state.dragWoId = tr.dataset.woId;
        state.dragSource = "unscheduled";
        if (!e.dataTransfer) return;
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", state.dragWoId);
        e.dataTransfer.setData("application/x-unscheduled-wo", state.dragWoId);
        const id = tr.dataset.woId;
        const wo = state.latestWorkOrders.find((w) => String(w.id) === String(id));
        if (!wo) return;
        const resourceId = String(wo.trade || "");
        const color = getTradeColor(resourceId);
        const dragEl = document.createElement("div");
        dragEl.className = "fc-daygrid-event fc-daygrid-block-event fc-h-event fc-event";
        dragEl.style.cssText = "background-color:" + color + ";border-color:" + color + ";position:absolute;top:-1000px;left:-1000px;";
        const inner = buildWorkOrderContent(wo.id, resourceId, wo.equipment || "", wo.description || "", wo.type || "", !!wo.safety);
        dragEl.appendChild(inner);
        document.body.appendChild(dragEl);
        const rect = dragEl.getBoundingClientRect();
        e.dataTransfer.setDragImage(dragEl, rect.width / 2, rect.height / 2);
        setTimeout(() => document.body.removeChild(dragEl), 0);
      });
    });
  }

  SchedulePage.populateResourceSelect = populateResourceSelect;
  SchedulePage.updateTradeViews = updateTradeViews;
})();
