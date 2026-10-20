# Story map — AutoHDR Photo-to-Video

```mermaid
---
config:
  layout: elk
  flowchart:
    nodeSpacing: 40
    rankSpacing: 60
---
flowchart LR
    S01["S01 Skeleton on Railway"]
    S02["S02 Passphrase, scrubbing"]
    S03["S03 Styles and songs"]
    S04["S04 Files and bucket"]
    S05["S05 Media"]
    S06["S06 Providers: chat"]
    S07["S07 Providers: video"]
    S08["S08 Photoshoots"]
    S09["S09 Draft and shot plan"]
    S10["S10 Queue and job routes"]
    S29["S29 Worker interface"]
    S11["S11 Restart, redo, edits"]
    S12["S12 Pipeline: prepare shot"]
    S28["S28 Pipeline: attempts, fallbacks"]
    S30["S30 Pipeline: deadline, stops, assembly"]
    S13["S13 Comparison"]
    S14["S14 Evals command"]
    S15["S15 Styles + New video screens"]
    S16["S16 Jobs + Job screens"]
    S17["S17 Editor screen"]
    S18["S18 Create style + compare screens"]
    S19["S19 README and scaling"]
    S20["S20 Wire: upload a photoshoot"]
    S21["S21 Wire: style to shot plan"]
    S22["S22 Wire: make the video"]
    S23["S23 Wire: failures, restart, redo"]
    S24["S24 Wire: editor re-export"]
    S25["S25 Wire: create and reproduce a style"]
    S26["S26 Wire: evals on 12 shoots"]
    S27["S27 Demo ready"]

    S01 --> S02 & S03 & S04 & S05 & S06 & S07 & S08 & S09 & S10 & S12 & S13 & S14 & S15 & S16 & S17 & S18 & S19 & S28 & S29 & S30
    S09 & S29 --> S11
    S02 & S04 & S05 & S06 & S08 & S15 --> S20
    S03 & S07 & S09 & S20 --> S21
    S05 & S07 & S10 & S12 & S13 & S16 & S21 & S28 & S29 & S30 --> S22
    S11 & S22 --> S23
    S11 & S17 & S22 --> S24
    S18 & S22 --> S25
    S14 & S19 & S25 --> S26
    S23 & S24 & S25 --> S27

    classDef demo fill:#fde2e1,stroke:#c0392b,color:#000
    classDef module fill:#eeeeee,stroke:#777,color:#000
    classDef held stroke-dasharray:5 4
    class S01,S20,S21,S22,S23,S24,S25,S26,S27 demo
    class S02,S03,S04,S05,S06,S07,S08,S09,S10,S11,S12,S13,S14,S15,S16,S17,S18,S19,S28,S29,S30 module
    class S01,S20,S21,S25,S26 held
```

Arrows point from a story to the stories it unblocks. Red = human demo (story 1 and wiring stories); grey = module story checked by agents. Dashed border = planning waits on a blocker below (outside setup the candidate does).
Demo order: S01 → S20 then S21 (one long window) → S22 → S23 + S24 + S25 (one window) → S27 → S26.

## Blockers
| # | Blocks stories | What is needed | Who decides | Source |
|---|---|---|---|---|
| 1 | S01 (deploy) | Railway Hobby account, one bucket per environment, bucket CORS for the app's address and localhost | Candidate, under an hour, start now | STACK §16 |
| 2 | S20 and every real call after it | OpenRouter key with credits for Nano Banana, Gemini, Claude and Seedance; BYOK for Veo on; a Google Cloud budget alert (an alert, not a limit: GC-3 sets no spend limit) | Candidate, under an hour, before the 10-19 morning window | STACK §16, GC-3 |
| 3 | S20, S26 | The 12 test shoots downloaded from the PRD's Dropbox link to a folder outside the repo (GC-9) | Candidate | GC-6, GC-9 |
| 4 | S21, S25, S26 | 2–3 BY-NC or BY-NC-SA songs picked from Free Music Archive, licences recorded in the seed manifest; 2–3 preset style texts | Candidate, a few hours, by 10-18 evening (S21 is demoed in the 10-19 morning window) | STACK §16, GC-5 |
| 5 | GC-1 if the demo windows are fewer | The timeline needs the long window on 10-19 and two windows a day (Timeline) | Candidate | Timeline |
| 6 | S01, S08, S09, S11, S15, S16, S22 (sizes) | These run 12–18 criteria, above the skill's "about 8". Kept whole after two review rounds: each is one module's operations or one flow, and a split would add a story with no seam of its own. Splitting S15 (Styles vs New video) and S11 (restart and redo vs editor) is the first move if a build pass overruns | Candidate | Final review, 2026-10-18 |

## Order
| # | Story | Kind | Blocked by | Review gate | Size | Checked by |
|---|---|---|---|---|---|---|
| 1 | S01 Skeleton on Railway | skeleton | none | human demo | L | Demo: deployed Styles page from stubs, `/healthz`, stub routes, green gate, empty metrics report |
| 2 | S02 Passphrase and log scrubbing | module | S01 | agents | M | pytest: requests with and without the passphrase; scrubbed logs |
| 3 | S03 Styles and songs | module | S01 | agents | M | pytest on the Library routes and seed command |
| 4 | S04 Files and bucket | module | S01 | agents | M | pytest with moto |
| 5 | S05 Media | module | S01 | agents | M | pytest on generated images, clips and a test tone |
| 6 | S06 Providers: chat | module | S01 | agents | L | pytest with mocked OpenRouter; hand-run live tests |
| 7 | S07 Providers: video | module | S01 | agents | L | pytest with mocked Videos API; one hand-run live clip |
| 8 | S08 Photoshoots | module | S01 | agents | M | pytest with stubbed Files, Media, labeller |
| 9 | S09 Draft and shot plan | module | S01 | agents | M | pytest with a stub planner |
| 10 | S10 Queue and job routes | module | S01 | agents | M | pytest on the four routes with seeded jobs |
| 11 | S29 Worker interface | module | S01 | agents | M | pytest on the interface, threads at once |
| 12 | S12 Pipeline: prepare shot | module | S01 | agents | M | pytest running the worker on stubs |
| 13 | S28 Pipeline: attempts and fallbacks | module | S01 | agents | M | pytest with scripted checks and errors |
| 14 | S30 Pipeline: deadline, stops, assembly | module | S01 | agents | M | pytest with a fake clock |
| 15 | S13 Comparison | module | S01 | agents | M | pytest with seeded jobs and a stub cut detector |
| 16 | S15 Styles and New video screens | module | S01 | agents | M | Playwright on stubbed routes |
| 17 | S16 Jobs and Job screens | module | S01 | agents | M | Playwright on stubbed routes |
| 18 | S17 Editor screen | module | S01 | agents | M | Playwright on stubbed routes |
| 19 | S18 Create style and compare screens | module | S01 | agents | M | Playwright on stubbed routes |
| 20 | S11 Restart, redo, edits | module | S09, S29 | agents | M | pytest with seeded finished and stopped jobs |
| 21 | S14 Evals command | module | S01 | agents | M | pytest on synthetic shoots and seeded jobs |
| 22 | S19 README and scaling | module | S01 | agents | S | Agent follows README setup; scaling sections checked |
| 23 | S20 Wire: upload a photoshoot | wiring | S02, S04, S05, S06, S08, S15 | human demo | M | Demo: drop a test shoot, see refused files and room labels |
| 24 | S21 Wire: style to shot plan | wiring | S03, S07, S09, S20 | human demo | M | Demo: create presets → edit text → real plan → edit cards → save as my style |
| 25 | S22 Wire: make the video | wiring | S05, S07, S10, S12, S13, S16, S21, S28, S29, S30 | human demo | L | Demo: real job, second job waits, play, download, credit, metrics |
| 26 | S23 Wire: failures, restart, redo | wiring | S11, S22 | human demo | M | Demo: injected failures locally; worker restart and Redo on the deployed app |
| 27 | S24 Wire: editor re-export | wiring | S11, S17, S22 | human demo | M | Demo: edit shots, re-export remakes 2, within 10 min |
| 28 | S25 Wire: create and reproduce a style | wiring | S18, S22 | human demo | M | Demo: write a style, try it, set reference, reproduce, side by side |
| 29 | S27 Demo ready | wiring | S23, S24, S25 | human demo | S | Demo: live Veo check, live flow, demo job made and played offline, deploys frozen |
| 30 | S26 Wire: evals on 12 shoots | wiring | S14, S19, S25 | human demo | M | Demo: preset references, EV-1 and EV-2 runs, reviewed sheet, report, metrics, README results |

## Timeline
Capacity: 5 agents at once (the lazy-orchestrator's limit) **[assumed]**; two demo windows a day, about 9 AM and 8 PM local, with the 10-19 morning window long enough (about 45 min) to demo S20, wait for S21 to build and demo S21 **[assumed]**; start 2026-10-18 evening. The candidate is the reviewer for EV-1 and EV-2 and needs about 2 h to watch and mark about 20 videos **[assumed]**. Dates move with the windows.
Total: agent time 330–680 min (about 5.5–11.3 h), plus generation time for real jobs (below); last required demo 2026-10-21 morning (likely) to 2026-10-21 evening (high).

| # | Story | Agent minutes (likely – high) | Built by (likely – high) | Demoed in window | Needed for |
|---|---|---|---|---|---|
| 1 | S01 | 20 – 45 | 10-18 evening, after blocker 1 | W1 10-18 evening | everything |
| 2–22 | S02–S19, S28–S30 (module stories, 5 at a time; S11 after S09 and S29) | 225 – 460 in total, about 50 – 110 elapsed | 10-18 night | — (agents) | the wiring stories |
| 23 | S20 | 10 – 20 | 10-18 night | W2 10-19 morning (first half) | S21 |
| 24 | S21 | 10 – 20 | during W2 | W2 10-19 morning (second half) | S22 |
| 25 | S22 | 20 – 45, plus two real jobs of 10–30 min | 10-19 afternoon | W3 10-19 evening | S23, S24, S25 |
| 26 | S23 | 10 – 20, plus short local and real jobs | 10-19 night | W4 10-20 morning | S27 |
| 27 | S24 | 10 – 20, plus one re-export of up to 10 min | 10-19 night | W4 10-20 morning | S27 |
| 28 | S25 | 10 – 20, plus three real jobs of 10–30 min | 10-19 night | W4 10-20 morning | S26, S27 |
| 29 | S27 | 5 – 10, plus the demo job (10–30 min) | 10-20 afternoon | W5 10-20 evening | GC-1, DE-4 |
| 30 | S26 | 10 – 20, plus about 4–6 reference tries and 16–18 eval jobs run one at a time (3.3–12 h), then about 2 h of review | 10-20 afternoon to 10-21 midday | W6 10-21 morning (likely) or W7 10-21 evening (high) | GC-8, EV-1, EV-2 |

| External wait | Needed by story | Lead time | Start by |
|---|---|---|---|
| Railway account, buckets, CORS | S01 | under 1 h | now (10-18) |
| OpenRouter credits, BYOK, Google Cloud budget alert | S06/S07 live tests, S20 | under 1 h | 10-18 evening |
| Download the 12 test shoots | S20, S26 | under 1 h | 10-18 evening |
| Pick 2–3 CC songs and write 2–3 preset texts | S21, S25, S26 | a few hours | 10-18 evening |
| Live Veo call on the demo day | S27 | minutes | 10-21 |

| Deadline | Date | Requires | Stories | Done by (high) | Status |
|---|---|---|---|---|---|
| GC-1 submission | 2026-10-21 11:59 PM local *(assumed)* | Every requirement; "try to drop nothing" (USERS §8) | S01–S30 | W7, 10-21 evening | **At risk.** Met on the high estimate only with the assumed windows, with one spare window (W6) on the likely estimate and none on the high one. With one window a day the last demo lands about 10-24 |

## Design tradeoffs
| # | Change | Documents changed | Rows checked (number, why it holds) | Saves | Cost later | Decision |
|---|---|---|---|---|---|---|
| 1 | Order and review, no design change: S20 and S21 in one long window; S23, S24 and S25 in one window; S27 no longer waits for the evals | none (story order only) | none touched | 2 demo windows (about 1 day) | none | applied as an ordering choice under "Make your best assumptions" |
| 2 | More demo time: a midday window on 10-19 and 10-20 | none | none touched | 2 more spare windows; GC-1 becomes met with margin | 2 × 10 min of the candidate's time | pending: the candidate's call |

No design tradeoff (component, technology or module) is proposed: the demos, not the build, set the pace, and no component is ahead of a requirement due by GC-1.

## Architecture coverage
| Element | Kind | ARCHITECTURE section | Owning story | Criterion | Extended by |
|---|---|---|---|---|---|
| listStyles `GET /api/styles` | route | Library → API | S03 | 4 | — |
| getStyle `GET /api/styles/{id}` | route | Library → API | S03 | 9 | — |
| listSongs `GET /api/songs` | route | Library → API | S03 | 1 | — |
| createStyle `POST /api/styles` | route | Library → API | S03 | 3 | — |
| updateStyle `PUT /api/styles/{id}` | route | Library → API | S03 | 8 | — |
| createUpload `POST /api/photoshoots` | route | Photoshoots → API | S08 | 1 | — |
| completeUpload `POST /api/photoshoots/{id}/complete` | route | Photoshoots → API | S08 | 4 | — |
| getPhotoshoot `GET /api/photoshoots/{id}` | route | Photoshoots → API | S08 | 6 | — |
| createJob `POST /api/jobs` | route | Jobs → API | S09 | 1 | — |
| replanJob `POST /api/jobs/{id}/plan` | route | Jobs → API | S09 | 9 | — |
| updateJobShots `PUT /api/jobs/{id}/shots` | route | Jobs → API | S09 | 7 | — |
| submitJob `POST /api/jobs/{id}/submit` | route | Jobs → API | S10 | 1 | — |
| listJobs `GET /api/jobs` | route | Jobs → API | S10 | 5 | — |
| getJob `GET /api/jobs/{id}` | route | Jobs → API | S10 | 2, 4 | — |
| getVideo `GET /api/jobs/{id}/video` | route | Jobs → API | S10 | 6, 7 | — |
| restartJob `POST /api/jobs/{id}/restart` | route | Jobs → API | S11 | 1 | — |
| redoShot `POST /api/jobs/{id}/shots/{position}/redo` | route | Jobs → API | S11 | 3 | — |
| editShot `PATCH /api/jobs/{id}/shots/{position}` | route | Jobs → API | S11 | 5 | — |
| exportJob `POST /api/jobs/{id}/export` | route | Jobs → API | S11 | 11, 12 | — |
| setReference `POST /api/styles/{id}/reference` | route | Comparison → API | S13 | 5 | — |
| getReproduction `GET /api/styles/{id}/reproductions/{jobId}` | route | Comparison → API | S13 | 7 | — |
| `GET /healthz` | route | System-wide contracts → Health | S01 | 2 | S02 (stays open) |
| labelPhotoshoot (and relabel on app start) | job | Photoshoots → Jobs and messages | S08 | 6, 8 | — |
| planJob (and re-plan on app start) | job | Jobs → Jobs and messages | S09 | 2, 12 | — |
| runNextJob (worker loop) | job | Pipeline → Jobs and messages | S12 | 1 | S28, S30 |
| Startup recovery, worker side | job | Data flows → Startup recovery | S30 | 8 | — |
| songs seed command | job | Library → `songs` | S03 | 1, 2 | — |
| `evals import` | job | Evals | S14 | 1 | — |
| `evals run --suite ev1 / ev2` | job | Evals | S14 | 2, 3 | — |
| `evals report` | job | Evals | S14 | 6, 7, 10, 11 | — |
| Pipeline per-shot steps 1–3 (crop, edit chain, check, retry, image fallback, prompt, clip length) | job | Pipeline → What it does per pending shot | S12 | 2–7 | — |
| Pipeline per-shot steps 4–5 (clip, check, attempts, video model fallback) | job | Pipeline → What it does per pending shot | S28 | 1–4 | — |
| Pipeline assembly of passed shots not removed | job | Pipeline → assemble | S30 | 1, 6 | — |
| submitJob refused with nothing to make | route error | Jobs → API | S10 | 3 | — |
| Re-export with only re-cut changes (no pending shot) | job | Key decisions; Pipeline | S30 | 10 | S24 (5) |
| `video_version` +1 on every finished re-run | measurement | `jobs` | S29 | 11 | S23 (7) |
| Speed change needs a new clip | route rule | Jobs → editShot (see architectural issue 8) | S11 | 15 | S24 (8) |
| `songs` | table | Database schema | S03 | 1 | — |
| `styles` | table | Database schema | S03 | 3 | — |
| `photoshoots` | table | Database schema | S08 | 1 | — |
| `photos` | table | Database schema | S08 | 4 | — |
| `jobs` | table | Database schema | S09 | 1 | S10, S29, S11 |
| `job_shots` | table | Database schema | S09 | 2 | S29, S11 |
| `attempts` | table | Database schema | S29 | 3 | — |
| `provider_calls` | table | Database schema | S06 | 8 | S07 |
| `cut_checks` | table | Database schema | S13 | 1 | — |
| Library.getStyle | interface | Library → Interface | S03 | 9 | — |
| Library.setReferenceJob | interface | Library → Interface | S03 | 10 | — |
| Photoshoots.listPhotos | interface | Photoshoots → Interface | S08 | 9 | — |
| Photoshoots.importPhotoshoot | interface | Photoshoots → Interface | S08 | 10 | — |
| Jobs.claimNextJob | interface | Jobs → Interface | S29 | 1 | — |
| Jobs.recoverInterrupted | interface | Jobs → Interface | S29 | 8 | — |
| Jobs.setShotState | interface | Jobs → Interface | S29 | 7 | — |
| Jobs.setShotPhoto | interface | Jobs → Interface | S29 | 5 | — |
| Jobs.startAttempt | interface | Jobs → Interface | S29 | 3 | — |
| Jobs.finishAttempt | interface | Jobs → Interface | S29 | 12 | — |
| Jobs.setShotResult | interface | Jobs → Interface | S29 | 4 | — |
| Jobs.finishJob | interface | Jobs → Interface | S29 | 9, 10 | — |
| Jobs.stopJob | interface | Jobs → Interface | S29 | 6 | — |
| Jobs createJob / submitJob for Evals | interface | Jobs → Interface | S09 / S10 | 1, 13 / 1 | S26 |
| Providers.labelPhotos | interface | Providers → Interface | S06 | 1 | — |
| Providers.planShots | interface | Providers → Interface | S06 | 2, 3 | — |
| Providers.editPhoto | interface | Providers → Interface | S06 | 4 | — |
| Providers.checkEdit | interface | Providers → Interface | S06 | 5 | — |
| Providers.checkClip | interface | Providers → Interface | S06 | 6 | — |
| Providers.generateClip | interface | Providers → Interface | S07 | 1, 2 | — |
| Providers.allowedLengths | interface | Providers → Interface | S07 | 3 | — |
| Providers.recoverCalls | interface | Providers → Interface | S07 | 6 | — |
| FakeProviders test double | interface | Providers → Calls out | S06 | 11 | S07 (8) |
| Media.crop16x9 | interface | Media | S05 | 1 | — |
| Media.thumbnail | interface | Media | S05 | 2 | — |
| Media.extractFrames | interface | Media | S05 | 3 | — |
| Media.probe | interface | Media | S05 | 6 | — |
| Media.assemble | interface | Media | S05 | 4, 5, 7 | — |
| Media.detectCuts | interface | Media | S05 | 4 | — |
| Files.presignUpload | interface | Files | S04 | 1, 2 | — |
| Files.presignDownload | interface | Files | S04 | 3, 4 | — |
| Files.put / get | interface | Files | S04 | 8 | — |
| Files.headObject | interface | Files | S04 | 5 | — |
| Comparison.recordCuts | interface | Comparison → Interface | S13 | 1–4 | S30 (7) |
| Bucket key layout | external | Files → Calls out | S04 | 1, 8 | — |
| OpenRouter chat completions (edit, plan, checks, labels) | external | Providers → Calls out | S06 | 1–7 | — |
| OpenRouter Videos API | external | Providers → Calls out | S07 | 1, 2, 4 | — |
| Railway Storage Bucket (real) | external | Environments | S20 | 1 | — |
| Styles screen (cards, reference mark, Make a reproduction) | screen | HLD §5 Web client | S15 | 1, 2, 17, 18 | — |
| New video screen (text, song and preview, upload, labels, plan, failed plan) | screen | HLD §5 Web client | S15 | 2–16 | — |
| Jobs screen | screen | HLD §5 Web client | S16 | 1, 2 | — |
| Job screen (all states) | screen | HLD §5 Web client | S16 | 3–12 | — |
| Editor screen | screen | HLD §5 Web client | S17 | 1–10 | — |
| Create a style screen | screen | HLD §5 Web client | S18 | 1–6 | — |
| Reference and reproduction screen | screen | HLD §5 Web client | S18 | 7–10 | — |
| Access (passphrase) | system-wide | Access | S02 | 1–4 | — |
| Error format | system-wide | System-wide contracts | S01 | 6 | — |
| Times | system-wide | System-wide contracts | S16 | 13 | — |
| Database (foreign keys, busy timeout) | system-wide | System-wide contracts | S01 | 14 | — |
| Blocking work | system-wide | System-wide contracts | S01 | 15 | — |
| Scrubbing | system-wide | System-wide contracts | S02 | 5, 6 | S04 (7), S06 (10) |
| Backup and restore: none required; the offline demo copy is DE-4 | system-wide | System-wide contracts | S27 | 3 | — |
| Processes | system-wide | System-wide contracts | S01 | 7 | — |
| Configuration and `.env.example` | system-wide | System-wide contracts | S01 | 8 | — |
| Environments (Local, Test and CI, Production) | system-wide | Environments and the regression gate | S01 | 1, 9, 13 | S27 (4) |
| Regression gate | system-wide | Environments and the regression gate | S01 | 9–11, 16 | every story |
| Metrics report (one panel per metric) | measurement | Measurement | S01 | 12 | S22 (10), S23 (10), S26 (11) |
| Video wait time timestamps | measurement | Measurement | S10 / S29 | 1 / 9 | — |
| Time to tell the user about a provider error | measurement | Measurement | S28 | 6 | — |
| Regeneration attempts per shot | measurement | Measurement | S29 | 3 | — |
| Re-export time | measurement | Measurement | S11 | 14 | S24 (3) |
| Shots dropped because every attempt was flagged | measurement | Measurement | S28 | 2 | — |
| Cut-time error | measurement | Measurement | S13 | 1 | — |
| Cost per call and per job | measurement | Measurement | S06 | 8, 9 | S07 (5), S29 (9) |
| Reviewer sheet | measurement | Measurement | S14 | 4, 5 | — |
| Access: no route but `/healthz` without the passphrase | Must hold | Access | S02 | 1 | — |
| Access: passphrase never logged | Must hold | Access | S02 | 5 | — |
| Only the owner writes each table (all modules) | Must hold | every module | S01 | 16 | — |
| Library: a style holds text and a song only | Must hold | Library | S03 | 11 | S25 (7) |
| Library: songs are BY-NC or BY-NC-SA | Must hold | Library | S03 | 2 | — |
| Library: updating a style never changes a job | Must hold | Library | S09 | 10 | — (the job side holds it; S03 only writes styles) |
| Photoshoots: no photo over 25 MB or another type | Must hold | Photoshoots | S08 | 2, 5 | — |
| Photoshoots: a photo's file key never changes | Must hold | Photoshoots | S08 | 12 | — |
| Photoshoots: photos never in the repository | Must hold | Photoshoots | S01 | 11 | S26 (8) |
| Jobs: at most one job running | Must hold | Jobs | S01 | 4 | S29 (1) |
| Jobs: a job's copied shot fields never change | Must hold | Jobs | S09 | 10 | see architectural issue 2 |
| Jobs: at most 4 attempts per shot per round | Must hold | Jobs | S29 | 3 | — |
| Jobs: a failed shot has a reason and is listed | Must hold | Jobs | S29 | 4 | — |
| Jobs: never ready with a shot pending or in flight | Must hold | Jobs | S29 | 10 | — |
| Jobs: only the final passed clip is returned | Must hold | Jobs | S10 | 4 | — |
| Jobs: a re-export never changes an untouched shot | Must hold | Jobs | S11 | 13 | S24 (4) |
| Jobs: departures from the plan are shown on the shot | Must hold | Jobs | S16 | 8 | S22 (12) |
| Pipeline: a clip is used only if its check passed | Must hold | Pipeline | S28 | 1 | — |
| Pipeline: one shot failing never stops the others | Must hold | Pipeline | S30 | 1 | — |
| Pipeline: provider errors reported within 60 s | Must hold | Pipeline | S28 | 6 | S23 (1) |
| Pipeline: no clip after the deadline | Must hold | Pipeline | S30 | 2 | — |
| Pipeline: temporary files never on the volume | Must hold | Pipeline | S12 | 8 | — |
| Providers: API key only in the request header | Must hold | Providers | S06 | 10 | S07 (9) |
| Providers: no clip left undownloaded | Must hold | Providers | S07 | 6 | S23 (4) |
| Media: cuts are re-encoded | Must hold | Media | S05 | 4 | — |
| Files: the bucket is private | Must hold | Files | S04 | 6 | S20 (demo step 4) |
| Files: presigned links never logged | Must hold | Files | S04 | 7 | — |
| Comparison: a reference is a ready job from the style's text | Must hold | Comparison | S13 | 6 | — |
| Jobs failure: submit while another job runs | failure behaviour | Jobs → Failure behaviour | S10 | 2 | — |
| Jobs failure: worker restarted mid-job | failure behaviour | Jobs → Failure behaviour | S29 | 8 | S23 (3) |
| Pipeline failure: rate limited or timeout | failure behaviour | Pipeline → Failure behaviour | S28 | 5 | — |
| Pipeline failure: provider refuses | failure behaviour | Pipeline → Failure behaviour | S28 | 3 | — |
| Pipeline failure: out of credit | failure behaviour | Pipeline → Failure behaviour | S30 | 3 | S23 (1) |
| Pipeline failure: all 4 attempts flagged | failure behaviour | Pipeline → Failure behaviour | S28 | 2 | — |
| Pipeline failure: deadline reached | failure behaviour | Pipeline → Failure behaviour | S30 | 2 | — |
| Pipeline failure: assembly fails | failure behaviour | Pipeline → Failure behaviour | S30 | 5 | — |
| No shot passed → stopped | failure behaviour | Pipeline | S30 | 4 | — |
| Labelling failure → `label_failed` | failure behaviour | Photoshoots → Jobs and messages | S08 | 7 | S20 (5) |
| Plan failure → asked again once, then `failed` | failure behaviour | Jobs → planJob | S09 | 5, 6 | S21 (8) |
| recordCuts failure never fails the job | failure behaviour | Comparison → Interface | S13 | 3 | — |
| Media failure → MediaError | failure behaviour | Media | S05 | 8 | — |
| Provider errors → one set of kinds | failure behaviour | Providers → Calls out | S06 | 7 | S07 (4, 7) |

## Flow coverage
| Data flow (ARCHITECTURE trace) | Wiring story | Stubs it removes | Integration cases added to the gate |
|---|---|---|---|
| createUpload, browser upload, completeUpload, getPhotoshoot ("Upload a photoshoot") | S20 | Files, Media, labelPhotos in Photoshoots; Photoshoots routes behind New video | upload, complete, label with real Providers on mocked OpenRouter, labelling error |
| listStyles, getStyle, listSongs, createStyle, createJob, replanJob, updateJobShots | S21 | getStyle, listPhotos, planShots, allowedLengths in Jobs; presignDownload in Library; Library and Jobs routes behind Styles and New video | createJob through planJob, invalid plan, missing style |
| submitJob, listJobs, getJob, getVideo, "Run next job" ("Make the video") | S22 | Jobs interface, Providers, Media, Files, recordCuts in Pipeline (S12, S28, S30); presignDownload in Jobs; detectCuts and Files.get in recordCuts; Jobs routes behind Jobs and Job; submitJob behind New video | full job with a flagged attempt and a failed shot |
| restartJob, redoShot, "Startup recovery" | S23 | restartJob and redoShot behind the Job screen | restart, redo, recovery; out of credit, rate limit, refusal |
| editShot, exportJob | S24 | getJob, getPhotoshoot, editShot, exportJob behind the Editor | edit and export, invalid edit, busy job |
| updateStyle, setReference, getReproduction, createJob with purpose reproduction ("Reproduce a style and compare") | S25 | routes behind Create a style and Reference and reproduction, and the Styles card's "Make a reproduction"; Photoshoots in Library; setReferenceJob, Files, Media in Comparison's routes | createStyle, setReference, getReproduction; not-ready reference, no reference |
| Evals | S26 | importPhotoshoot, createJob, submitJob in Evals (the last stubs) | import and run, a stopped job; the no-stub check |
| Production on demo day | S27 | none (only the Evals stubs remain, removed by S26) | the no-stub check outside Evals |

## Requirement coverage
| Requirement | Kind | Threshold (quoted) | Story (or milestone) | Criterion |
|---|---|---|---|---|
| GC-1 | given | "complete by 2026-10-21, 11:59 PM local time" | Timeline (deadline, no work) | — |
| GC-2 | given | "One builder" | Timeline (team, no work) | — |
| GC-3 | given | "No spend limit is set for now" | S06 | 8, 12 |
| GC-4 | given | approved list, or a free tier | S01 | 10 |
| GC-5 | given | "BY-NC or BY-NC-SA, not ND … shown with the video" | S03; S22 | 2; 7 |
| GC-6 | given | "The 12 PRD test photoshoots are the test set" | S26 | 1, 3 |
| GC-7 | given | written explanation of scaling | S19 | 3 |
| GC-8 | given | README with setup, design and results | S19; S26 | 1, 2; 7 |
| GC-9 | given | test photos "never committed to the repository" | S01; S26 | 11; 8 |
| FR-1.1 | functional | — | S20 | 1 |
| FR-1.2 | functional | — | S21 | 2, 10 |
| FR-1.3 | functional | — | S22 | 4 |
| FR-1.4 | functional | — | S22 | 1, 6 |
| FR-1.5 | functional | — | S23 | 1, 2 |
| FR-1.6 | functional | — | S23 | 5, 6 (see architectural issue 1) |
| FR-1.7 | functional | — | S22 | 8 |
| FR-1.8 | functional | — | S22 | 12 |
| FR-1.9 | functional | — | S22 | 13 |
| FR-1.10 | functional | — | S21 | 3, 5, 6, 11 |
| FR-1.11 | functional | — | S22 | 4 |
| FR-1.12 | functional | — | S23 | 7 |
| FR-1.13 | functional | — | S24 | 1 |
| FR-1.14 | functional | — | S24 | 1, 8 |
| FR-1.15 | functional | — | S24 | 5, 9 |
| FR-1.16 | functional | — | S24 | 2, 4 |
| FR-2.1 | functional | — | S25 | 1, 2 |
| FR-2.2 | functional | — | S25 | 3 |
| FR-2.3 | functional | — | S25 | 4 |
| FR-2.4 | functional | — | S25 | 4, 5, 6 |
| FR-2.5 | functional | — | S21; S25 | 7; 4 |
| FR-3.2 | functional | — | S20 | 6 |
| FR-3.3 | functional (exclusion) | — | Icebox | — |
| FR-3.4 | functional (exclusion) | — | Icebox | — |
| FR-3.5 | functional (exclusion) | — | Icebox | — |
| FR-3.6 | functional (Gate) | — | S25 | 7 |
| VR-1 | non-functional | "At most 2 visibly AI-generated shots per delivered video; target 0" | S26 | 5, 10 |
| VR-2 | non-functional | "cuts land within ±0.1 s of the shot plan's cut times" | S22; S25 | 6; 6 |
| VR-3 | non-functional | "100% of shots move as their plan says … 100% of the movements, transitions and pacing the style text names appear in the plan" | S21; S26 | 4; 5 |
| VR-4 | non-functional | "[tbd]; interim target 100% … floor 80%" | S26 | 5 |
| VR-5 | non-functional | "0 generated shots or edited photos add, remove or change a room, fixture or architectural feature" | S26; S12 | 5, 10; 4 |
| VR-6 | non-functional | "100% of transitions in the video match the shot plan" | S26 | 5 |
| PF-1 | non-functional | "within 30 min of submitting" | S22; S26 | 1; 3 |
| PF-2 | non-functional | "Typical jobs finish within 10 min" | S26 | 11 |
| PF-3 | non-functional | regeneration uses "at most the remainder" of 30 min | S30 | 2 |
| PF-4 | non-functional | "up to 2 changed shots is playable within 10 min" | S24 | 3 |
| RL-1 | non-functional | "reported to the user within 60 s" | S23; S28 | 1, 10; 6 |
| RL-2 | non-functional | "100% of failed shots appear in the result with a reason" | S29; S23 | 4; 6 |
| RL-3 | non-functional | "never stops the other shots" | S30; S23 | 1; 5 |
| OB-1 | non-functional | style, photo, prompts, model, attempts, result, total time | S22 | 9 |
| OB-2 | non-functional | every rejected shot "with the check's score" | S22 | 9 |
| QC-1 | non-functional | "[tbd]; interim target: catches ≥ 60%" | S26 | 6 |
| QC-2 | non-functional | "regenerated up to 3 times" | S29; S28 | 3; 2 |
| SC-1 | non-functional | "Supports 1 job at a time … a second job … is queued" | S22 | 3 |
| SC-2 | non-functional | what changes to run N jobs within PF-1 | S19 | 3, 4 |
| DE-1 | non-functional | "current desktop Chrome release" | S01 | 1 |
| DE-2 | non-functional | "JPG and PNG, up to 40 photos and 25 MB each" | S08; S20 | 2, 3; 3, 4, 8 |
| DE-3 | non-functional | "without a GPU requirement" | S01 | 13 |
| DE-4 | non-functional | live, or "a pre-generated job is shown" | S27 | 2, 3 |
| DE-5 | non-functional | "1920×1080, 16:9 landscape, at the style's frame rate" | S05; S22 | 6; 5 |
| EV-1 | non-functional | 12 test shoots, per-video report | S26 | 3 |
| EV-2 | non-functional | each preset on ≥ 2 other shoots | S26 | 2, 4 |
| CO-1 | non-functional | cost per call and per job; list price for BYOK; an outside-list call stops at its free limit | S06; S07; S29; S01 | 8, 9; 5; 9; 10 (no outside-list service is configured, so the stop case cannot arise) |
| CH-1 | non-functional | edit one shot "without regenerating the others" | S24 | 4 |
| CH-2 | non-functional | two jobs on separate capacity, "outputs match single-job runs" | S30 | 9 |

## Metric coverage
| Metric | Data it needs | Story that records it | Dashboard panel (story 1) | Wiring demo that shows it with real data |
|---|---|---|---|---|
| Video wait time (slowest), PF-1 | `first_submitted_at`, `first_finished_at` | S10, S29 | metrics report panel 1 | S22 (criterion 10) |
| Video wait time (typical), PF-2 | same | S10, S29 | panel 2 | S26 (criterion 11) |
| Time to tell the user about a provider error, RL-1 | `provider_calls.finished_at`, `attempts.finished_at`, `jobs.finished_at` | S28 | panel 3 | S23 (criterion 10), on injected errors in the local instance |
| Regeneration attempts per shot, QC-2 | `attempts` per shot and round | S29 | panel 4 | S22 (criterion 10) |
| Shots dropped because every attempt was flagged, VR-1 proxy | `job_shots.failure_reason` | S28 | panel 5 | S22 (criterion 10) |
| Cut-time error against the style, VR-2 | `cut_checks.error_s` | S13 | panel 6 | S22 (criterion 10) |

## Assumptions
- ARCHITECTURE A-1: Pipeline owns no tables and writes through Jobs — S12, S28, S29, S30.
- Capacity: 5 agents at once, two demo windows a day and a long window on 10-19 morning — the whole timeline; with one window a day GC-1 is missed.
- ARCHITECTURE A-2: a style's reference video is the author's approved run on the demo shoot — S13, S25, S26.
- ARCHITECTURE A-3 and A-10: labelling and planning run in the app process — S08, S09.
- ARCHITECTURE A-4: a rate limit counts as one of a shot's 4 attempts — S28 criterion 5.
- ARCHITECTURE A-5: a job with no passing shot is stopped — S30 criterion 4.
- ARCHITECTURE A-6: songs are added by a seed command — S03 criterion 1.
- ARCHITECTURE A-7: the 30-minute budget runs from when the worker claims the job — S29 criterion 2, S30 criterion 2.
- ARCHITECTURE A-8: a clip recovered after a restart is kept but not reused — S07, S23.
- ARCHITECTURE A-9: the fallback video model takes over after a refusal or two failures — S28 criteria 3, 4.
- ARCHITECTURE open question 2 [verify]: Gemini accepts the clip inline — S06 (checkClip); if not, frames only, same ClipCheck.
- ARCHITECTURE open question 6 [verify]: Railway enforces presigned size limits — S04, S20; completeUpload's check covers either way.
- ARCHITECTURE open question 7 [verify]: BYOK is marked in the response — S06, S07; otherwise the `BYOK_MODELS` setting.
- The metrics "dashboard" is a report command over the tables, since STACK §13 says every metric is a query over the job log tables — S01, S22, S23, S26.
- Preset styles are written by the candidate from the wireframe's examples and created through createStyle — S21, S26.
- `evals import` reuses a shoot already uploaded with the same label, so a preset's demo shoot (uploaded in S21) is the same row EV-2 skips — S14 criterion 1, S21, S26.
- A speed change remakes the clip, because speed is part of the prompt (Pipeline step 2) — S11 criterion 15, S24 criterion 8.
- Injected failures are demoed on a local instance with `FAKE_PROVIDERS=1`, since production uses real providers only — S23.

## Icebox
- FR-3.3 creator ratings, reviews, payments, credits — REQUIREMENTS FR-3, USERS §7.
- FR-3.4 phone layout — REQUIREMENTS FR-3, USERS §7.
- FR-3.5 past-video upload and storyboard-outline authoring — REQUIREMENTS 0a #5.
- A spend limit — GC-3 and ARCHITECTURE open question 12 put it later.
- Several workers and a real queue — HLD §5 "What to add next"; only described in S19.

## Feasibility checks
- OpenRouter Videos API with Veo 3.1 and Seedance 2.0 makes 1080p clips from a first frame, 12 in flight, 48–88 s each — `VIDEO_RESEARCH.md` §7 and `tools/gen_clip.py`, run 2026-10-17/18.
- The stack's pieces fit together — STACK.md compatibility check, 2026-10-18.
- Not checked live: the planner's plan quality (ARCHITECTURE open question 1) and Gemini clip input (open question 2); both are first exercised in S21 and S22.
- Fresh review of this story set, 2026-10-18: round 1, 17 findings, all applied; round 2, 16 findings, all applied except oversized stories (Blocker 6) and a few multi-step Whens.

## Architectural issues
1. **FR-1.6 vs assembly — resolved 2026-10-18.** The candidate said "make the best decision"; FR-1.6 now reads "delivered without that shot, and the job page marks the failed shot and its reason beside the video", matching the architecture. Was: "the rest of the video is still delivered with the failed shot marked". ARCHITECTURE Pipeline: "A failed or skipped shot leaves its slot out and the video is marked `ready_with_failures`". The stories mark the failed shot on the Job page beside the player (S16 criterion 7, S23 criterion 6), not inside the video. An amendment would reword FR-1.6 to "marked on the job page" or have assembly keep a marked slot.
2. **Jobs Must hold "copied shot fields never change after creation (CH-1)" — resolved 2026-10-19 by S11.** ARCHITECTURE Jobs Must hold now reads "change only through updateJobShots before submit and editShot after". It conflicts with the editor: editShot changes shot fields after a job finishes (FR-1.13–FR-1.16), and the same section says plan fields change "after that only by editShot". The stories test what the rest of the architecture means: a job keeps its own text and plan when a style changes (S09 criterion 10), and an untouched shot never changes on re-export (S11 criterion 13).
3. **The Job type has no video version.** Re-export and redo raise `video_version`, and S23 and S24 show "the version goes up", but `Job.video` carries only `{ url, durationS, width, height }`. An amendment would add `version` to `Job.video`.
4. **The Evals reviewer sheet has no VR-3 or VR-4 column.** ARCHITECTURE Evals lists `visibly_ai, room_changed, movement_matches, transition_matches`; VR-3 needs "reviewer checks each plan against its text" and VR-4 a side-by-side judgment. S14 adds a "text followed" row per plan and a "looks like the reference" row per reproduction (criterion 5). An amendment would add both to the Evals contract. Applied by S14: the ARCHITECTURE Evals contract now lists both rows.
5. **Library → Providers.allowedLengths has no contract.** The summary diagram draws `library -->|allowedLengths| providers` (and `library -->|listPhotos| shoots`), but no Library operation uses clip lengths. The stories stub Photoshoots in Library for the demo shoot check (S03, removed by S25) and do not build the allowedLengths edge. An amendment would remove the edge or name the Library operation that needs it.
6. **STACK §16 lists an OpenRouter key spend limit**, which conflicts with GC-3 ("No spend limit is set for now"). The stories keep only a budget alert (Blocker 2). An amendment to STACK §16 would drop the limit or mark it as a safety net needing the candidate's OK.
7. **A preset's demo shoot can only be set when it is created.** ARCHITECTURE updateStyle accepts "any of { name, styleText, songId, songOffsetS, fps }", without `demoPhotoshootId`. The stories create each preset with its demo shoot in S21. An amendment would let updateStyle set the demo shoot.
8. **Speed is not in editShot's "needs a new clip" list — resolved 2026-10-19 by S11.** ARCHITECTURE editShot and FR-1.16 now list speed. ARCHITECTURE editShot marks a new clip "if the photo, movement, prompts or photo edit changed", and FR-1.16 says the same. But speed is part of the clip prompt (Pipeline step 2), so S11 criterion 15 treats a speed change as needing a new clip.
