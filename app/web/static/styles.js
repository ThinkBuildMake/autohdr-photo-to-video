document.querySelectorAll("form.repro").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const alert = form.querySelector("[role=alert]");
    alert.textContent = "";
    try {
      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          photoshootId: form.photoshoot.value,
          styleText: form.dataset.styleText,
          songId: form.dataset.songId,
          styleId: form.dataset.styleId,
          purpose: "reproduction",
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.message);
      location.href = "/new?jobId=" + encodeURIComponent(body.job.id);
    } catch (error) {
      alert.textContent = (error instanceof TypeError ? "" : error.message) || "The reproduction could not start.";
    }
  });
});
