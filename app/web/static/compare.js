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

function render(c) {
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
  const length = (t) => (t ? seconds(t.lengthS) : "–");
  const error = (t) => {
    if (!t || t.cutErrorS === null) return "–";
    return seconds(t.cutErrorS) + (Math.abs(t.cutErrorS) > 0.1 ? " over" : "");
  };
  document.getElementById("shots").replaceChildren(
    ...c.shots.map((shot) => {
      const tr = row([
        shot.position,
        `${words(shot.movementName)} · ${words(shot.transition)}`,
        length(shot.reference),
        length(shot.reproduction),
        `${error(shot.reference)} / ${error(shot.reproduction)}`,
        shot.flagged ? "Flagged" : "",
      ]);
      if (shot.flagged) tr.classList.add("flag");
      return tr;
    }),
  );
  document.getElementById("worst-cut").textContent =
    c.maxCutErrorS === null ? "No cut was measured." : `Worst cut error: ${seconds(c.maxCutErrorS)}`;
  document.getElementById("comparison").hidden = false;
}

document.getElementById("play-both").addEventListener("click", () => {
  for (const video of document.querySelectorAll("#comparison video")) {
    video.currentTime = 0;
    video.play().catch(() => {});
  }
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
    render(await getJson(`/api/styles/${page.styleId}/reproductions/${picked.id}`));
  } catch (error) {
    show(
      error.code === "no_reference"
        ? "This style has no reference video yet. Try it on Create a style and keep the try you like as its reference."
        : error.message,
    );
  }
}

load().catch((error) => show(error.message));
