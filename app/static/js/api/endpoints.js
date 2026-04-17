/**
 * Central registry of backend endpoint URLs for the frontend.
 *
 * Non-module scripts rely on `window.Endpoints`.
 */
(function () {
  "use strict";

  // Avoid overwriting if already defined (e.g., hot reload).
  window.Endpoints = window.Endpoints || {};

  window.Endpoints.optimize = "/api/optimize";
  window.Endpoints.optimizeXlsx = "/api/optimize/xlsx";
  window.Endpoints.saveScheduleHints = "/api/schedule/hints";
  window.Endpoints.chat = "/api/agent/chat";

  window.Endpoints.shifts = {
    list: "/api/shifts",
    byTrade: function (trade) {
      return "/api/shifts/" + encodeURIComponent(trade);
    },
    create: "/api/shifts",
    update: function (trade) {
      return "/api/shifts/" + encodeURIComponent(trade);
    },
    del: function (trade) {
      return "/api/shifts/" + encodeURIComponent(trade);
    },
  };
})();

