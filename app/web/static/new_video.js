const $ = (selector, root = document) => root.querySelector(selector);

async function api(method, url, body) {
  const response = await fetch(url, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || `The request failed (${response.status}).`);
  return data;
}

$("#start-from").addEventListener("change", (event) => {
  const option = event.target.selectedOptions[0];
  if (!option.value) return;
  $("#style-text").value = option.dataset.text;
  $("#song").value = option.dataset.song;
});

$("#play-song").addEventListener("click", () => {
  const audio = $("#song-preview");
  audio.src = $("#song").selectedOptions[0].dataset.preview;
  audio.play();
});

const POLL_MS = 2000;
// createUpload's rule; its tickets are the accepted files in drop order.
const ACCEPTED_TYPES = ["image/jpeg", "image/png"];
const MAX_BYTES = 25 * 1024 * 1024;
const REASONS = { too_large: "too large", wrong_type: "wrong type", missing: "did not arrive" };
const LABEL_NOTES = {
  labelling: "Labelling the rooms…",
  ready: "Rooms labelled automatically.",
  label_failed: "The rooms are not labelled. The plan will be made from the photos alone.",
};
const roomName = (room) => (room ? room.replaceAll("_", " ") : "");
const state = { shoot: null, refused: [] };

function showRefused() {
  const refused = [
    ...state.refused,
    ...(state.shoot ? state.shoot.photos : [])
      .filter((p) => p.status !== "uploaded" && p.status !== "awaiting_upload")
      .map((p) => ({ name: p.originalName, reason: p.status })),
  ];
  const box = $("#refused");
  box.hidden = refused.length === 0;
  box.replaceChildren();
  if (!refused.length) return;
  const title = document.createElement("strong");
  title.textContent = `${refused.length} ${refused.length === 1 ? "file was" : "files were"} not added`;
  box.append(title);
  for (const file of refused) {
    const line = document.createElement("span");
    line.textContent = `${file.name}: ${REASONS[file.reason] || file.reason}`;
    box.append(line);
  }
}

function showShoot() {
  const photos = state.shoot.photos.filter((p) => p.status === "uploaded");
  $("#photo-summary").hidden = false;
  $("#photo-count").textContent = `${photos.length} ${photos.length === 1 ? "photo" : "photos"} ready`;
  $("#label-note").textContent = LABEL_NOTES[state.shoot.status] || "";
  $("#photo-grid").replaceChildren(
    ...photos.map((p) => {
      const tile = $("#tile").content.firstElementChild.cloneNode(true);
      $("img", tile).src = p.thumbUrl;
      $("img", tile).alt = p.originalName;
      $(".name", tile).textContent = p.originalName;
      $(".room", tile).textContent = roomName(p.room);
      $(".room", tile).hidden = !p.room;
      $(".subject", tile).textContent = p.subject || "";
      return tile;
    })
  );
  $("#next").disabled = photos.length === 0;
  $("#next-reason").textContent = photos.length ? "" : "Add photos to continue.";
  showRefused();
}

async function pollShoot() {
  while (state.shoot.status === "labelling") {
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    state.shoot = (await api("GET", `/api/photoshoots/${state.shoot.id}`)).photoshoot;
    showShoot();
  }
}

async function upload(fileList) {
  const files = [...fileList];
  if (!files.length) return;
  plan.job = null;
  plan.shots = [];
  state.shoot = null;
  state.refused = [];
  $("#upload-error").textContent = "";
  try {
    const created = await api("POST", "/api/photoshoots", {
      files: files.map((f) => ({ name: f.name, size: f.size, type: f.type })),
    });
    state.refused = created.refused;
    const accepted = files.filter((f) => ACCEPTED_TYPES.includes(f.type) && f.size <= MAX_BYTES);
    await Promise.allSettled(
      created.uploads.map((ticket, index) => {
        const file = accepted[index];
        const form = new FormData();
        for (const [key, value] of Object.entries(ticket.fields)) form.append(key, value);
        form.append("file", file);
        return fetch(ticket.url, { method: "POST", body: form });
      })
    );
    state.shoot = (await api("POST", `/api/photoshoots/${created.photoshootId}/complete`)).photoshoot;
    showShoot();
    await pollShoot();
  } catch (error) {
    $("#upload-error").textContent = error.message;
  }
}

const dropZone = $("#drop-zone");
dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("over"));
dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("over");
  upload(event.dataTransfer.files);
});
$("#photo-input").addEventListener("change", (event) => upload(event.target.files));

const PROMPTS = JSON.parse($("#movement-prompts").textContent);
const CHANGED = "changed_by_photographer";
const PLANNED_FIELDS = [
  "room", "photoId", "photoEditPrompts", "movementName", "movementPrompt", "speed",
  "model", "lengthS", "transition", "transitionS", "planNote",
];
const plan = { job: null, shots: [] };
const photoById = (id) => (state.shoot ? state.shoot.photos.find((p) => p.id === id) : undefined);

function cutTime(seconds) {
  const value = Math.round(seconds * 10);
  const minutes = Math.floor(value / 600);
  const wholeSeconds = String(Math.floor(value / 10) % 60).padStart(2, "0");
  return `${minutes}:${wholeSeconds}${value % 10 ? "." + value % 10 : ""}`;
}

function renderShots() {
  let elapsed = 0;
  const photos = state.shoot ? state.shoot.photos.filter((p) => p.status === "uploaded") : [];
  $("#plan-summary").textContent =
    `We turned your style text into a plan of ${plan.shots.length} shots. ` +
    "Change anything before the video is made.";
  $("#shots").replaceChildren(
    ...plan.shots.map((shot, index) => {
      const card = $("#shot-card").content.firstElementChild.cloneNode(true);
      const field = (name) => $(`[name=${name}]`, card);
      const photo = photoById(shot.photoId);
      elapsed += shot.photoId ? shot.lengthS : 0;
      $(".cut-time", card).textContent = `cut at ${cutTime(elapsed)}`;
      $(".shot-title", card).textContent = `Shot ${index + 1} · ${roomName(shot.room)}`;
      $(".shot-photo", card).hidden = !photo;
      if (photo) $(".shot-photo", card).src = photo.thumbUrl;
      field("photo").append(
        new Option("No photo (skip this shot)", ""),
        ...photos.map((p) => new Option(`${p.originalName}${p.room ? " · " + roomName(p.room) : ""}`, p.id))
      );
      field("photo").value = shot.photoId || "";
      field("movement").value = shot.movementName;
      field("speed").value = shot.speed;
      field("length").value = shot.lengthS;
      field("transition").value = shot.transition;
      field("edits").value = shot.photoEditPrompts.join("\n");
      $(".plan-note", card).textContent = shot.planNote === CHANGED ? "Changed by you" : shot.planNote;
      card.addEventListener("change", (event) => {
        const name = event.target.name;
        const value = event.target.value;
        if (name === "photo") {
          shot.photoId = value || null;
          shot.room = (photoById(value) || {}).room || shot.room;
        }
        if (name === "movement") Object.assign(shot, { movementName: value, movementPrompt: PROMPTS[value] });
        if (name === "speed") shot.speed = value;
        if (name === "length") shot.lengthS = Number(value);
        if (name === "transition") Object.assign(shot, { transition: value, transitionS: value === "cut" ? 0 : shot.transitionS || 0.5 });
        if (name === "edits") shot.photoEditPrompts = value.split("\n").map((s) => s.trim()).filter(Boolean);
        shot.planNote = CHANGED;
        renderShots();
      });
      field("remove").addEventListener("click", () => {
        plan.shots.splice(index, 1);
        renderShots();
      });
      return card;
    })
  );
}

function showPlan(job) {
  plan.job = job;
  plan.shots = job.shots.map((shot) => ({ ...shot }));
  $("#step-1").hidden = true;
  $("#step-2").hidden = false;
  $("#step-1-tab").classList.remove("on");
  $("#step-2-tab").classList.add("on");
  $("#plan-wait").hidden = job.planStatus !== "planning";
  $("#plan-failed").hidden = job.planStatus !== "failed";
  $("#plan-ready").hidden = job.planStatus !== "ready";
  $("#plan-failed .reason").textContent = job.planStatus === "failed" ? job.planNotes : "";
  $("#plan-notes").hidden = !(job.planStatus === "ready" && job.planNotes);
  $("#plan-notes .note").textContent = job.planNotes || "";
  if (job.planStatus === "ready") renderShots();
}

async function pollPlan(job) {
  showPlan(job);
  while (plan.job.planStatus === "planning") {
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    showPlan((await api("GET", `/api/jobs/${job.id}`)).job);
  }
}

async function savePlan() {
  const shots = plan.shots.map((shot, index) => {
    const planned = { position: index + 1 };
    for (const key of PLANNED_FIELDS) planned[key] = shot[key];
    return planned;
  });
  showPlan((await api("PUT", `/api/jobs/${plan.job.id}/shots`, { shots })).job);
}

async function report(action) {
  $("#plan-status").textContent = "";
  $("#page-error").textContent = "";
  try {
    await action();
  } catch (error) {
    $("#page-error").textContent = error.message;
  }
}

async function whileBusy(button, action) {
  button.disabled = true;
  try {
    await report(action);
  } finally {
    button.disabled = false;
  }
}

$("#next").addEventListener("click", (event) =>
  whileBusy(event.currentTarget, async () => {
    const body = {
      photoshootId: state.shoot.id,
      styleText: $("#style-text").value,
      songId: $("#song").value,
    };
    const created = plan.job
      ? await api("POST", `/api/jobs/${plan.job.id}/plan`, { styleText: body.styleText, songId: body.songId })
      : await api("POST", "/api/jobs", { ...body, styleId: $("#start-from").value || undefined });
    await pollPlan(created.job);
  })
);

$("#add-shot").addEventListener("click", () => {
  const photo = (state.shoot ? state.shoot.photos : []).find((p) => p.status === "uploaded");
  const last = plan.shots[plan.shots.length - 1];
  plan.shots.push({
    room: (photo && photo.room) || "other",
    photoId: photo ? photo.id : null,
    photoEditPrompts: [],
    movementName: "dolly_in",
    movementPrompt: PROMPTS.dolly_in,
    speed: "slow",
    model: last ? last.model : "google/veo-3.1",
    lengthS: 4,
    transition: "cut",
    transitionS: 0,
    planNote: CHANGED,
  });
  renderShots();
});

$("#save-plan").addEventListener("click", () =>
  report(async () => {
    await savePlan();
    $("#plan-status").textContent = "Plan saved";
  })
);

let submitting = false;
function setPlanDisabled(disabled) {
  $("#step-2").querySelectorAll("button, input, select, textarea").forEach((control) => {
    control.disabled = disabled;
  });
}
$("#make-video").addEventListener("click", async () => {
  if (submitting) return;
  submitting = true;
  setPlanDisabled(true);
  $("#page-error").textContent = "";
  try {
    await savePlan();
    setPlanDisabled(true);
    await api("POST", `/api/jobs/${plan.job.id}/submit`);
    location.href = `/jobs/${encodeURIComponent(plan.job.id)}`;
  } catch (error) {
    $("#page-error").textContent = error.message;
    submitting = false;
    setPlanDisabled(false);
  }
});

function backToStyle() {
  $("#step-1").hidden = false;
  $("#step-2").hidden = true;
  $("#step-1-tab").classList.add("on");
  $("#step-2-tab").classList.remove("on");
  $("#page-error").textContent = "";
  showShoot();
}
$("#back").addEventListener("click", backToStyle);
$("#replan").addEventListener("click", backToStyle);

$("#try-again").addEventListener("click", () =>
  report(async () => pollPlan((await api("POST", `/api/jobs/${plan.job.id}/plan`, {})).job))
);

const draftId = new URLSearchParams(location.search).get("jobId");
if (draftId) {
  report(async () => {
    const job = (await api("GET", `/api/jobs/${encodeURIComponent(draftId)}`)).job;
    state.shoot = (await api("GET", `/api/photoshoots/${job.photoshootId}`)).photoshoot;
    $("#style-text").value = job.styleText;
    showShoot();
    await pollPlan(job);
  });
}

$("#save-style").addEventListener("click", async () => {
  const name = $("#style-name").value.trim();
  const result = $("#save-result");
  if (!name) {
    result.textContent = "Give the style a name first.";
    return;
  }
  try {
    await api("POST", "/api/styles", {
      name,
      authorName: "you",
      styleText: $("#style-text").value,
      songId: $("#song").value,
    });
    result.textContent = `Saved as ${name}`;
  } catch (error) {
    result.textContent = error.message;
  }
});
