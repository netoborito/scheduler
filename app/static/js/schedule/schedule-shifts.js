/**
 * Shifts, colors, availability, and work-order UI helpers. Depends: schedule-state, schedule-utils.
 */
(function () {
  "use strict";
  const SchedulePage = window.SchedulePage;
  const state = SchedulePage.state;
  const formatDateLocalYMD = SchedulePage.formatDateLocalYMD;

  const TRADE_COLORS = [
    "#22c55e", "#3b82f6", "#a855f7", "#ec4899", "#f97316",
    "#eab308", "#06b6d4", "#facc15", "#4ade80", "#f472b6",
  ];

  const DAY_NAMES = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
  ];

  function getManHoursForDate(dateStr) {
    if (!dateStr || !state.latestWorkOrders.length) return 0;
    const woById = new Map(state.latestWorkOrders.map((wo) => [String(wo.id), wo]));
    let total = 0;
    for (const ev of state.currentCalendarEvents) {
      let evDate = "";
      if (ev.start) {
        evDate = typeof ev.start === "string"
          ? ev.start.slice(0, 10)
          : formatDateLocalYMD(new Date(ev.start));
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

  function getAvailableManHoursForDate(dateStr) {
    if (!dateStr || !state.shiftAvailability.length) return null;
    const d = new Date(dateStr + "T12:00:00");
    if (Number.isNaN(d.getTime())) return null;
    const dayIndex = (d.getDay() + 6) % 7;
    const dayKey = DAY_NAMES[dayIndex];
    const selectEl = document.getElementById("resource-select");
    const selectedResource = selectEl ? selectEl.value : "";
    let total = 0;
    for (const shift of state.shiftAvailability) {
      if (!shift[dayKey]) continue;
      if (selectedResource && shift.trade !== selectedResource) continue;
      total += Number(shift.technicians_per_crew || 1) * Number(shift.shift_duration_hours || 0);
    }
    return total;
  }

  function getTradeColor(trade) {
    if (!trade) return "#6b7280";
    if (state.shiftColors[trade]) return state.shiftColors[trade];
    let hash = 0;
    const s = String(trade);
    for (let i = 0; i < s.length; i++) hash = (hash * 31 + s.charCodeAt(i)) | 0;
    return TRADE_COLORS[Math.abs(hash) % TRADE_COLORS.length];
  }

  function getTypeBadgeInfo(type, safety) {
    const t = (type || "").toLowerCase();
    if (safety) return { text: "S", className: "type-safety" };
    if (t.includes("preventive")) return { text: "PM", className: "type-pm" };
    if (t.includes("planned")) return { text: "P", className: "type-p" };
    if (t.includes("process")) return { text: "PI", className: "type-pi" };
    if (t.includes("corrective")) return { text: "C", className: "type-c" };
    if (t.includes("ehs")) return { text: "EHS", className: "type-ehs" };
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

  SchedulePage.getManHoursForDate = getManHoursForDate;
  SchedulePage.getAvailableManHoursForDate = getAvailableManHoursForDate;
  SchedulePage.getTradeColor = getTradeColor;
  SchedulePage.getTypeBadgeInfo = getTypeBadgeInfo;
  SchedulePage.buildWorkOrderContent = buildWorkOrderContent;
})();
