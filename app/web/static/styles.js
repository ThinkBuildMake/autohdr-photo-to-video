document.querySelectorAll("form.repro").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (form.dataset.busy) return;
    form.dataset.busy = "yes";
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    const alert = form.querySelector("[role=alert]");
    alert.textContent = "";
    try {
      const saved = await fetch(`/api/styles/${form.dataset.styleId}`);
      const detail = await saved.json();
      if (!saved.ok) throw new Error(detail.message);
      const style = detail.style;
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          photoshootId: form.photoshoot.value,
          styleText: style.styleText,
          songId: style.song.id,
          styleId: form.dataset.styleId,
          purpose: "reproduction",
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.message);
      location.href = "/new?jobId=" + encodeURIComponent(body.job.id);
    } catch (error) {
      delete form.dataset.busy;
      button.disabled = false;
      alert.textContent = (error instanceof TypeError ? "" : error.message) || "The reproduction could not start.";
    }
  });
});

const selected = new URLSearchParams(location.search).get("reproduce");
for (const form of document.querySelectorAll("form.repro")) {
  if (form.dataset.styleId === selected) {
    form.closest("details").open = true;
    form.scrollIntoView();
  }
}
