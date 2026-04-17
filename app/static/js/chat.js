/**
 * Collapsible LLM chat panel. Depends: endpoints.js (window.Endpoints.chat).
 */
(function () {
  "use strict";

  var messages = [];
  var busy = false;

  var panel = document.getElementById("chat-panel");
  var toggle = document.getElementById("chat-toggle");
  var body = document.getElementById("chat-body");
  var input = document.getElementById("chat-input");
  var sendBtn = document.getElementById("chat-send");

  toggle.addEventListener("click", function () {
    panel.classList.toggle("open");
    if (panel.classList.contains("open")) input.focus();
  });

  sendBtn.addEventListener("click", send);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });

  function appendBubble(role) {
    var div = document.createElement("div");
    div.className = "chat-bubble chat-" + role;
    body.appendChild(div);
    body.scrollTop = body.scrollHeight;
    return div;
  }

  function send() {
    var text = input.value.trim();
    if (!text || busy) return;
    input.value = "";
    messages.push({ role: "user", content: text });
    appendBubble("user").textContent = text;

    busy = true;
    sendBtn.disabled = true;
    var bubble = appendBubble("assistant");
    bubble.textContent = "";

    var url = (window.Endpoints && window.Endpoints.chat) || "/api/agent/chat";
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: messages }),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Chat request failed");
        return readSSE(res, bubble);
      })
      .catch(function (err) {
        bubble.textContent = "Error: " + err.message;
      })
      .finally(function () {
        busy = false;
        sendBtn.disabled = false;
      });
  }

  function triggerScheduleRefresh() {
    var resourceSelect = document.getElementById("resource-select");
    var savedResource = resourceSelect ? resourceSelect.value : "";
    var form = document.getElementById("optimize-form");
    if (form) {
      form.requestSubmit();
      if (savedResource && resourceSelect) {
        setTimeout(function () { resourceSelect.value = savedResource; }, 500);
      }
    }
  }

  function readSSE(response, bubble) {
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "";
    var full = "";
    var needsRefresh = false;

    function pump() {
      return reader.read().then(function (result) {
        if (result.done) {
          messages.push({ role: "assistant", content: full });
          if (needsRefresh) triggerScheduleRefresh();
          return;
        }
        buffer += decoder.decode(result.value, { stream: true });

        var parts = buffer.split("\n\n");
        buffer = parts.pop();
        for (var i = 0; i < parts.length; i++) {
          var line = parts[i];
          if (line.indexOf("data: ") !== 0) continue;
          var payload = line.slice(6);
          if (payload === "[DONE]") continue;
          if (payload === "[REFRESH]") { needsRefresh = true; continue; }
          full += payload;
          bubble.textContent = full;
          body.scrollTop = body.scrollHeight;
        }
        return pump();
      });
    }

    return pump();
  }
})();
