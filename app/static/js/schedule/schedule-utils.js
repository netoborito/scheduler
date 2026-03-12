/**
 * Date and comparison utilities. Depends: schedule-state.js
 */
(function () {
  "use strict";
  const SchedulePage = window.SchedulePage;
  if (!SchedulePage) throw new Error("Load schedule-state.js first");

  function formatDateLocalYMD(d) {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function formatDateDisplay(isoOrYmd) {
    if (!isoOrYmd) return "";
    const d = new Date(isoOrYmd);
    if (Number.isNaN(d.getTime())) return isoOrYmd;
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const yy = String(d.getFullYear()).slice(-2);
    return `${mm}/${dd}/${yy}`;
  }

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
    if (key === "priority" || key === "duration" || key === "people") {
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

  SchedulePage.formatDateLocalYMD = formatDateLocalYMD;
  SchedulePage.formatDateDisplay = formatDateDisplay;
  SchedulePage.compareValues = compareValues;
})();
