(() => {
  const root = document.querySelector(".ed");
  const byPos = (selector, pos) => root.querySelector(`${selector}[data-position="${pos}"]`);
  const tiles = [...root.querySelectorAll(".tl")];

  const clock = (s) => {
    const [whole, tenths] = (s % 60).toFixed(1).split(".");
    return `${Math.floor(s / 60)}:${whole.padStart(2, "0")}${tenths === "0" ? "" : `.${tenths}`}`;
  };
  const OFFLINE = "Could not reach the server; ";
  let saves = Promise.resolve();
  const pending = new Map();

  function changeText(tile) {
    if (tile.dataset.removed === "true") return "removed";
    return { new_clip: "will be made again", recut_only: "only re-cut" }[tile.dataset.pending] || "unchanged";
  }

  function paint() {
    let total = 0;
    for (const tile of tiles) {
      const pos = tile.dataset.position;
      const removed = tile.dataset.removed === "true";
      const length = Number(tile.dataset.length);
      tile.classList.toggle("gone", removed);
      tile.querySelector(".tl-len").textContent = `${length.toFixed(1)} s`;
      tile.querySelector(".tl-change").textContent = changeText(tile);
      const seg = byPos(".seg", pos);
      seg.hidden = removed;
      seg.style.flexGrow = length;
      byPos("form", pos).querySelector(".remove").textContent =
        removed ? "Put this room back" : "Remove this room from the video";
      if (!removed) total += length;
    }
    root.querySelector(".song-total").textContent = clock(total);
    const count = (text) => tiles.filter((t) => changeText(t) === text).length;
    const remade = count("will be made again");
    const removed = count("removed");
    root.querySelector(".export-note").textContent =
      `${remade} shot${remade === 1 ? "" : "s"} will be made again, ${count("only re-cut")} only re-cut` +
      `${removed ? `, ${removed} removed` : ""}; the rest are reused and the video is re-cut to the song.`;
  }

  const exportButton = root.querySelector(".export");
  exportButton.addEventListener("click", async () => {
    const note = root.querySelector(".export-note");
    exportButton.disabled = true;
    await saves;
    if (root.querySelector(".field-error:not(:empty)")) {
      note.textContent = "Some changes were not saved. Fix the fields marked in red, then re-export.";
      exportButton.disabled = false;
      return;
    }
    try {
      const res = await fetch(`/api/jobs/${root.dataset.jobId}/export`, { method: "POST" });
      if (res.ok) {
        location.href = `/jobs/${root.dataset.jobId}`;
        return;
      }
      const data = await res.json().catch(() => ({ message: res.statusText }));
      note.textContent = data.message;
    } catch {
      note.textContent = `${OFFLINE}the video was not re-exported.`;
    }
    exportButton.disabled = false;
  });

  function pick(tile) {
    for (const t of tiles) t.classList.toggle("on", t === tile);
    for (const grid of root.querySelectorAll(".ed-grid")) grid.hidden = grid.dataset.position !== tile.dataset.position;
  }

  function save(form, body, field) {
    const key = `${form.dataset.position}:${field}`;
    pending.set(key, (pending.get(key) || 0) + 1);
    saves = saves.then(() => send(form, body, field, key)).catch((e) => console.error(e));
  }

  async function send(form, body, field, key) {
    const pos = form.dataset.position;
    const tile = byPos(".tl", pos);
    const error = form.querySelector(`.field-error[data-for="${field}"]`);
    error.textContent = "";
    let res, data;
    try {
      try {
        res = await fetch(`/api/jobs/${root.dataset.jobId}/shots/${pos}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        data = await res.json().catch(() => ({ message: res.statusText }));
      } catch {
        data = { message: `${OFFLINE}the change was not saved.` };
      }
      const stillQueued = (name) =>
        (pending.get(`${pos}:${name}`) || 0) > (name === field ? 1 : 0);
      if (!res?.ok || !data.shot) {
        const later = (pending.get(key) || 0) > 1;
        error.textContent = data.message;
        if (field === "removed" && !later) form.dataset.wantRemoved = tile.dataset.removed;
        if (field === "movementName" && !later) {
          form.elements.movementName.value = form.dataset.savedMovement;
          if (!stillQueued("movementPrompt")) {
            form.elements.movementPrompt.value = form.dataset.savedPrompt;
            error.textContent = "";
          }
        }
        return;
      }
      const warning = form.querySelector(".save-warning");
      warning.textContent = data.warning || "";
      warning.hidden = !data.warning;
      const promptMatchesSave = form.elements.movementPrompt.value === form.dataset.savedPrompt ||
        form.elements.movementPrompt.value === body.movementPrompt;
      form.dataset.savedMovement = data.shot.movementName;
      form.dataset.savedPrompt = data.shot.movementPrompt;
      if (!stillQueued("movementName")) form.elements.movementName.value = data.shot.movementName;
      if (!stillQueued("movementPrompt") && promptMatchesSave) {
        form.elements.movementPrompt.value = data.shot.movementPrompt;
      }
      if (!stillQueued("movementName") && !stillQueued("movementPrompt")) {
        form.querySelector('.field-error[data-for="movementName"]').textContent = "";
      }
      tile.dataset.pending = data.shot.pendingChange;
      tile.dataset.removed = data.shot.removed;
      tile.dataset.length = data.shot.lengthS;
      paint();
    } finally {
      pending.set(key, (pending.get(key) || 1) - 1);
    }
  }

  function editBody(form, field) {
    const value = form.elements[field].value;
    if (field === "lengthS") return { lengthS: Number(value) };
    if (field === "transition") return { transition: value, transitionS: value === "crossfade" ? 0.4 : 0 };
    if (field === "photoEditPrompts") return { photoEditPrompts: value.split("\n").map((s) => s.trim()).filter(Boolean) };
    if (field === "movementName") {
      const prompt = form.elements.movementPrompt;
      prompt.value = form.elements.movementName.selectedOptions[0].dataset.prompt;
      return { movementName: value, movementPrompt: prompt.value };
    }
    return { [field]: value };
  }

  for (const form of root.querySelectorAll("form.shot-form")) {
    form.addEventListener("submit", (e) => e.preventDefault());
    form.addEventListener("change", (e) => save(form, editBody(form, e.target.name), e.target.name));
    form.dataset.wantRemoved = byPos(".tl", form.dataset.position).dataset.removed;
    form.dataset.savedMovement = form.elements.movementName.value;
    form.dataset.savedPrompt = form.elements.movementPrompt.value;
    form.querySelector(".remove").addEventListener("click", () => {
      form.dataset.wantRemoved = String(form.dataset.wantRemoved !== "true");
      save(form, { removed: form.dataset.wantRemoved === "true" }, "removed");
    });
  }
  for (const tile of tiles) tile.addEventListener("click", () => pick(tile));
  pick(tiles[0]);
  paint();
})();
