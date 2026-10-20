// Create a style: write the style, try it on the demo shoot, revise, keep a try as the reference.
const form = document.getElementById("style-form");
const errorBox = document.getElementById("error");
const status = document.getElementById("try-status");
const tryBox = document.getElementById("try");
const video = tryBox.querySelector("video");
const useReference = document.getElementById("use-reference");
const tryButton = form.querySelector("button[type=submit]");
const POLL_MS = 5000;
const FINISHED = ["ready", "ready_with_failures", "stopped"];
let styleId = null;
let tries = 0;
let current = null;

async function api(method, url, body) {
  const response = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body && JSON.stringify(body),
  });
  const json = response.headers.get("content-type")?.includes("application/json");
  const data = json ? await response.json() : {};
  if (!response.ok) {
    throw new Error(data.message || `The server answered ${response.status} ${response.statusText}.`);
  }
  return data;
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = !message;
}

function words(code) {
  const text = code.replaceAll("_", " ");
  return text[0].toUpperCase() + text.slice(1);
}

function sourceLink(url) {
  const link = document.createElement("a");
  link.href = url;
  link.textContent = "source";
  link.target = "_blank";
  link.rel = "noopener";
  return link;
}

form.elements.songId.addEventListener("change", () => {
  const song = form.elements.songId.selectedOptions[0].dataset;
  const credit = document.getElementById("song-credit");
  credit.replaceChildren();
  if (song.source) credit.append(`${song.licence} · ${song.credit} · `, sourceLink(song.source));
});

function describe(job) {
  if (job.planStatus === "planning") return "writing the shot plan…";
  if (job.planStatus === "failed") return `the plan could not be written. ${job.planNotes || ""}`;
  if (job.status === "draft" || job.status === "queued") return "waiting to make the video…";
  if (job.status === "running") return "making the video…";
  if (job.status === "stopped") return `stopped (${words(job.stopReason || "stopped")}).`;
  return "";
}

function render(job) {
  const ready = job.status === "ready" || job.status === "ready_with_failures";
  status.textContent = ready
    ? `Try ${tries} is ready${job.status === "ready_with_failures" ? ", with shots that did not work" : ""}.`
    : `Try ${tries}: ${describe(job)}`;
  tryBox.hidden = job.planStatus !== "ready";
  document.getElementById("try-title").textContent = `Try ${tries} · video`;
  document.getElementById("plan-rows").replaceChildren(
    ...job.shots
      .filter((shot) => !shot.removed)
      .map((shot) => {
        const row = document.createElement("tr");
        const transition =
          shot.transition === "cut" ? "Cut" : `${words(shot.transition)} ${shot.transitionS} s`;
        for (const cell of [shot.position, words(shot.room), words(shot.movementName), `${shot.lengthS} s`, transition]) {
          row.insertCell().textContent = cell;
        }
        return row;
      }),
  );
  video.hidden = !job.video;
  if (job.video && video.getAttribute("src") !== job.video.url) video.src = job.video.url;
  const credit = document.getElementById("try-credit");
  credit.replaceChildren();
  if (job.video && job.songCredit) {
    const cut = job.songCredit.lastIndexOf(", ");
    credit.append(`Song: ${job.songCredit.slice(0, cut)} · `, sourceLink(job.songCredit.slice(cut + 2)));
  }
  useReference.disabled = job.status !== "ready";
}

async function follow(id) {
  for (let wait = 0; current === id; wait = POLL_MS) {
    await new Promise((resolve) => setTimeout(resolve, wait));
    if (current !== id) return;
    let job;
    try {
      job = (await api("GET", `/api/jobs/${id}`)).job;
    } catch (error) {
      if (current === id) showError(`${error.message} Checking again in a few seconds.`);
      continue;
    }
    if (current !== id) return;
    showError("");
    render(job);
    if (FINISHED.includes(job.status) || job.planStatus === "failed") return;
    if (job.planStatus === "ready" && job.status === "draft") {
      try {
        job = (await api("POST", `/api/jobs/${id}/submit`)).job;
      } catch (error) {
        if (current !== id) return;
        showError(error.message);
        return;
      }
      if (current !== id) return;
      render(job);
    }
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (tryButton.disabled) return;
  tryButton.disabled = true;
  const f = Object.fromEntries(new FormData(form));
  const style = { name: f.name, styleText: f.styleText, songId: f.songId, fps: Number(f.fps) };
  showError("");
  let job;
  try {
    const saved = styleId
      ? await api("PUT", `/api/styles/${styleId}`, style)
      : await api("POST", "/api/styles", {
          ...style,
          authorName: f.authorName,
          demoPhotoshootId: f.demoPhotoshootId,
        });
    styleId = saved.style.id;
    useReference.disabled = true;
    current = null;
    ({ job } = await api("POST", "/api/jobs", {
      photoshootId: f.demoPhotoshootId,
      styleText: f.styleText,
      songId: f.songId,
      styleId,
      purpose: "video",
    }));
  } catch (error) {
    showError(error.message);
    return;
  } finally {
    tryButton.disabled = false;
  }
  tries += 1;
  current = job.id;
  document.getElementById("reference-note").textContent = "";
  follow(job.id);
});

useReference.addEventListener("click", async () => {
  showError("");
  try {
    await api("POST", `/api/styles/${styleId}/reference`, { jobId: current });
    const link = document.createElement("a");
    link.href = `/styles/${styleId}/reproductions`;
    link.textContent = "See reproductions";
    document
      .getElementById("reference-note")
      .replaceChildren(`Try ${tries} is now the style's reference video. `, link);
  } catch (error) {
    showError(error.message);
  }
});
