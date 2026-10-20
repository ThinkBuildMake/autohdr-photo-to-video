// Times are sent in UTC and shown in the browser's local time, also after each HTMX refresh.
htmx.onLoad(function (root) {
  root.querySelectorAll("time[datetime]").forEach(function (el) {
    el.textContent = new Date(el.dateTime).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  });
});

// Start again and Redo: reload to show the queued job, or show the route's message in place.
// A failed refresh says so; the 5 s poll keeps going and its next good answer clears the message.
document.body.addEventListener("htmx:afterRequest", function (event) {
  var slot = document.querySelector(".action-error");
  if (!event.detail.elt.hasAttribute("hx-post")) {
    if (!event.detail.successful) slot.textContent = "Could not refresh this page. Still trying every 5 s.";
    return;
  }
  if (event.detail.successful) {
    location.reload();
    return;
  }
  var message = "Something went wrong. Try again.";
  try {
    message = JSON.parse(event.detail.xhr.responseText).message || message;
  } catch (e) {}
  slot.textContent = message;
});
