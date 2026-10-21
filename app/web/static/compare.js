// Reference and reproduction: a style's reference video beside one of its reproductions.
const page = document.getElementById("compare").dataset;
const message = document.getElementById("message");

async function getJson(url) {
  const response = await fetch(url);
  const json = response.headers.get("content-type")?.includes("application/json");
  const data = json ? await response.json() : {};
  if (!response.ok) {
    const text = data.message || `The server answered ${response.status} ${response.statusText}.`;
    throw Object.assign(new Error(text), { code: data.error });
  }
  return data;
}

function words(code) {
  const text = code.replaceAll("_", " ");
  return text[0].toUpperCase() + text.slice(1);
}

const seconds = (s) => `${Number(s.toFixed(2))} s`;
const clock = (s) => {
  const t = Math.round(s);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};
const counts = (used) =>
  Object.entries(used)
    .map(([code, n]) => (n > 1 ? `${words(code)} ×${n}` : words(code)))
    .join(", ");

function show(text) {
  message.textContent = text;
  message.hidden = false;
}

function row(cells) {
  const tr = document.createElement("tr");
  for (const cell of cells) tr.insertCell().textContent = cell;
  return tr;
}

function render(c, reference, reproduction) {
  document.getElementById("reference-title").textContent =
    `Reference video · ${c.reference.photoshootLabel || "demo shoot"}`;
  document.getElementById("reproduction-title").textContent =
    `Reproduction · ${c.reproduction.photoshootLabel || "another shoot"}`;
  document.getElementById("reference-video").src = c.reference.videoUrl;
  document.getElementById("reproduction-video").src = c.reproduction.videoUrl;
  const flagged = c.shots.filter((shot) => shot.flagged).length;
  document.getElementById("facts").textContent =
    `Same song: ${c.song.sameSong ? "yes" : "no"} · Same style text: ${c.sameText ? "yes" : "no"} · Shots flagged: ${flagged}`;
  const cut = c.song.credit.lastIndexOf(", ");
  const link = document.createElement("a");
  link.href = c.song.credit.slice(cut + 2);
  link.textContent = "source";
  link.target = "_blank";
  link.rel = "noopener";
  document.getElementById("song").replaceChildren(`Song: ${c.song.credit.slice(0, cut)} · `, link);

  const ref = c.summary.reference;
  const rep = c.summary.reproduction;
  document.getElementById("summary").replaceChildren(
    row(["Shots", ref.shotCount, rep.shotCount]),
    row(["Length", clock(ref.totalS), clock(rep.totalS)]),
    row(["Typical shot", seconds(ref.medianShotS), seconds(rep.medianShotS)]),
    row(["Movements", counts(ref.movements), counts(rep.movements)]),
    row(["Transitions", counts(ref.transitions), counts(rep.transitions)]),
  );
  const detail = (t, job, position) => {
    if (!t) return "–";
    const shot = job.shots.find((s) => s.position === position);
    return `${seconds(t.lengthS)} · ${words(shot.movementName)} · ${words(shot.transition)}`;
  };
  const error = (t) => {
    if (!t || t.cutErrorS === null) return "–";
    return seconds(t.cutErrorS) + (Math.abs(t.cutErrorS) > 0.1 ? " over" : "");
  };
  document.getElementById("shots").replaceChildren(
    ...c.shots.map((shot) => {
      const tr = row([
        shot.position,
        detail(shot.reference, reference, shot.position),
        detail(shot.reproduction, reproduction, shot.position),
        `${error(shot.reference)} / ${error(shot.reproduction)}`,
        shot.flagged ? "Flagged" : "",
      ]);
      if (shot.flagged) tr.classList.add("flag");
      return tr;
    }),
  );
  const worst = (side) => {
    // The first shown shot has no cut before it, so it is never "unmeasured".
    const cuts = c.shots.map((s) => s[side]).filter(Boolean).slice(1);
    const errors = cuts.map((t) => t.cutErrorS).filter((e) => e !== null);
    const missing = cuts.length - errors.length;
    if (!errors.length) return "No cut was measured.";
    const text = seconds(Math.max(...errors.map(Math.abs)));
    return missing ? `${text} (${missing} ${missing === 1 ? "cut" : "cuts"} not measured)` : text;
  };
  document.getElementById("worst-cut").textContent =
    `Worst cut error · Reference: ${worst("reference")} · Reproduction: ${worst("reproduction")}`;
  document.getElementById("comparison").hidden = false;
}

const videos = [...document.querySelectorAll("#comparison video")];
let linked = false;
let buffering = false;
let starting = false;
// Our own pause() still queues a "pause" event that can arrive after a restart; count and skip it.
const ownPauses = new Map();
function pauseTogether() {
  for (const v of videos) {
    if (v.paused) continue;
    ownPauses.set(v, (ownPauses.get(v) || 0) + 1);
    v.pause();
  }
}
async function startTogether() {
  if (starting) return;
  starting = true;
  try { await Promise.all(videos.map((v) => v.play())); }
  catch (error) {
    linked = false;
    pauseTogether();
    show(`Playback could not start: ${error.message || "Please try again."}`);
  } finally { starting = false; }
}
for (const video of videos) {
  const other = videos.find((v) => v !== video);
  video.addEventListener("pause", () => {
    if (ownPauses.get(video) > 0) return ownPauses.set(video, ownPauses.get(video) - 1);
    // A video that reached its end fires pause too; the longer one keeps playing.
    if (linked && !buffering && !starting && !video.ended) pauseTogether();
  });
  video.addEventListener("play", () => {
    if (linked && !buffering) startTogether();
  });
  video.addEventListener("seeking", () => {
    if (linked && Math.abs(other.currentTime - video.currentTime) > 0.05)
      other.currentTime = Math.min(video.currentTime, other.duration || video.currentTime);
  });
  video.addEventListener("waiting", () => {
    if (linked && !starting && !videos.every((v) => v.paused)) { buffering = true; pauseTogether(); }
  });
  video.addEventListener("canplay", () => {
    if (linked && buffering && videos.every((v) => v.readyState >= 3)) {
      buffering = false;
      startTogether();
    }
  });
}
setInterval(() => {
  if (linked && !buffering && videos.every((v) => !v.paused && !v.seeking) &&
      Math.abs(videos[0].currentTime - videos[1].currentTime) > 0.1)
    videos[1].currentTime = videos[0].currentTime;
}, 50);
document.getElementById("play-both").addEventListener("click", () => {
  linked = false;
  pauseTogether();
  videos.forEach((v) => { v.currentTime = 0; });
  linked = true;
  buffering = false;
  message.hidden = true;
  startTogether();
});

async function load() {
  const { jobs } = await getJson("/api/jobs");
  const reproductions = jobs.filter(
    (job) => job.purpose === "reproduction" && job.styleName === page.styleName,
  );
  if (!reproductions.length) return show("No reproductions of this style yet.");
  const wanted = new URLSearchParams(location.search).get("jobId");
  const finished = (job) => job.status === "ready" || job.status === "ready_with_failures";
  const picked =
    reproductions.find((job) => job.id === wanted) ||
    reproductions.find(finished) ||
    reproductions[0];
  document.getElementById("tabs").replaceChildren(
    ...reproductions.map((job) => {
      const tab = document.createElement("a");
      tab.href = `?jobId=${encodeURIComponent(job.id)}`;
      tab.className = job === picked ? "btn sm" : "btn alt sm";
      tab.textContent = job.photoshootLabel || "Untitled photoshoot";
      return tab;
    }),
  );
  try {
    const comparison = await getJson(`/api/styles/${page.styleId}/reproductions/${picked.id}`);
    const details = await Promise.all([comparison.reference, comparison.reproduction].map(
      (side) => getJson(`/api/jobs/${side.jobId}`),
    ));
    render(comparison, details[0].job, details[1].job);
  } catch (error) {
    show(
      error.code === "no_reference"
        ? "This style has no reference video yet. Try it on Create a style and keep the try you like as its reference."
        : error.message,
    );
  }
}

load().catch((error) => show(error.message));
