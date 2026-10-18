# STACK.md — AutoHDR Photo-to-Video technology choices

**What this document is.** A comparison of candidate technologies for each module, and the choice for each. `REQUIREMENTS.md` defines what the system must do; requirement IDs (e.g. `PF-1`) appear here only as the reason a choice wins or loses. Which components exist and the load they carry are in `HIGH_LEVEL_DESIGN.md`; how the pieces fit together is designed in `ARCHITECTURE.md`.

**How the shortlist was built.** Each module's options were researched against `REQUIREMENTS.md`, `HIGH_LEVEL_DESIGN.md`, `USERS.md`, `KEY_METRICS.md` and the 25 measured clips in `VIDEO_RESEARCH.md` §7, with deciding facts verified on 2026-10-18. No review meeting is available, so each module takes the recommended option (candidate: "make your best assumptions and move forward"). A separate agent that hadn't seen the research then checked the chosen stack for conflicts. It found that OpenRouter's Veo 3.1 runs on Google's general-release model, not the preview that shuts down on 2026-10-22. It added a shared passphrase, a process supervisor and frame extraction for the quality check, and raised requirement conflicts (§18). A later audit of every document against the PRD restored the PRD's photo edits (composition, lens, angle and light, architecture preserved), cut style authoring to one method, and set the output to 1080p; those changes are applied here and in `REQUIREMENTS.md`.

**Markers.** **[verify]** = an external fact checked on 2026-10-18 that should be re-confirmed before it's relied on. Go-live prerequisites, open choices and open questions are in the last sections.

---

## Summary

| # | Module | Choice | Main reason |
|---|---|---|---|
| 1 | Language and web framework | Python 3.13, FastAPI (current release, pinned in `uv.lock`), uv | One language with the research scripts and ffmpeg (GC-2) |
| 2 | Web client | Server-rendered Jinja2 pages + HTMX 2 | No build step; polling built in (FR-1.3, GC-1) |
| 3 | Database and job queue | SQLite (WAL) via SQLAlchemy 2.0; job table is the queue | 1 job at a time, < 10,000 rows (SC-1, HLD §5) |
| 4 | File storage | Railway Storage Bucket (S3 API, presigned links) | Holds 10–55 GB; a volume caps at 5 GB (HLD §2) |
| 5 | Hosting | Railway Hobby, one service, Dockerfile on `python:3.13-slim-trixie`, honcho running app + worker | Approved provider (GC-4); about $6–8/month |
| 6 | Video generation | OpenRouter Videos API, `google/veo-3.1` (Vertex, BYOK), 1080p, no audio, PRD starter-kit movement prompts; fallback `bytedance/seedance-2.0` | Measured best fit (VIDEO_RESEARCH §7.4); PF-1, DE-5 |
| 7 | Photo enhancement | Pillow crop to 16:9 + `google/gemini-nano-banana-2.1` with the PRD's cinematic and detail-shot prompts | FR-1.8 (composition, lens, angle, light); architecture preserved (VR-5) |
| 8 | Quality check and cut detection | `google/gemini-3.8-flash` given the clip plus frames at 4–8 per second; PySceneDetect 0.6.7.1 for cut times in finished videos | Catches brief figures (QC-1); measures cuts to ±0.1 s (VR-2) |
| 9 | Video assembly | ffmpeg 7.1 (Debian trixie) | The only tool needed to cut to the song (FR-1.4) |
| 10 | Songs | CC BY-NC or BY-NC-SA tracks from Free Music Archive | Licence recorded and credited per video (GC-5) |
| 11 | Access | One shared passphrase (HTTP basic auth), no accounts | Stops strangers starting paid jobs; FR-3.2 has no accounts |
| 12 | Secrets | Environment variables (Railway variables, `.env` locally) | Three secrets in total |
| 13 | Observability | Job log tables + platform stdout logs | OB-1, OB-2, CO-1 are rows, not dashboards |
| 14 | Testing | pytest + fake providers + moto (fake bucket); Playwright; eval script | Paid calls never run in tests; EV-1, EV-2 |
| 15 | CI/CD | GitHub Actions + Railway deploy from GitHub, "wait for CI" on | Free for this public repo |

**Cost (per job and per month; no limit is set, GC-3):**

| Item | Cost |
|---|---|
| Video, first pass: 8 shots × 4 s × $0.20/s (Veo 3.1 list price, the same at 720p and 1080p; billed by Google Cloud under BYOK) | $6.40 [verify] |
| Video, regenerations: up to 3 more attempts per shot (QC-2) | up to $19.20 more |
| Photo enhancement: 8 to 16 edits (the PRD example uses two edits for a detail shot) × about $0.04 (1K image, billed by OpenRouter) | $0.32–0.64 [verify] |
| Quality check: 8 to 32 calls × about $0.01 on Gemini 3.8 Flash | $0.08–0.32 [verify] |
| Hosting: Railway Hobby $5 (includes $5 usage) + about 0.5 GB RAM over that + bucket at $0.015/GB-month × 10–55 GB | $6–8/month [verify] |
| **Typical job (first pass, 4 s clips)** | **about $6.80** (about $10 if shots need 6 s clips) |
| **Worst case job (every shot regenerated 3 times)** | **about $26 with 4 s clips, about $52 with 8 s clips** — no limit is set; driven entirely by video seconds |
| **Project (under 50 jobs, HLD §2)** | **about $340–500 typical**, plus about $25 hosting |

The fallback Seedance 2.0 measured $0.76 per 5 s clip (§7.1): about $6 per first pass and $24 worst case, billed by OpenRouter.

---

## Glossary

`REQUIREMENTS.md` defines the product's own vocabulary — style, shot, visibly AI-generated shot, job, reproduction — and it isn't repeated here.

**AI services**

| Term | Meaning |
|---|---|
| OpenRouter | A company that resells many AI models behind one account and one key. We send it a request naming the model; it passes the request on and returns the result. |
| BYOK ("bring your own key") | An OpenRouter setting where the user stores their own key for a provider (here Google Cloud). Requests still go through OpenRouter, but the provider bills the user's own account directly. |
| Vertex AI | Google Cloud's paid service for running Google's AI models, billed to a Google Cloud project. |
| Veo 3.1 | Google's model that turns a photo plus a written instruction into a short video clip of 4, 6 or 8 seconds. |
| Seedance 2.0 | ByteDance's model that does the same job, with clips of 4 to 15 seconds. |
| First frame | The photo given to the video model as the clip's opening picture, so the clip starts in the real room. |
| Nano Banana 2.1 | The nickname for Google's image-editing model: it takes a photo and an instruction and returns an edited photo. |
| Gemini 3.8 Flash | A fast Google model that can watch a video and look at photos, then answer questions about them in text, such as "does a person appear?" |
| Preview model | A version a provider offers before it is final. Providers can switch preview versions off on a set date. |

**Video and files**

| Term | Meaning |
|---|---|
| ffmpeg | A free command-line program that cuts, joins and re-encodes video and audio files. |
| Re-encode | Rebuild a video's picture data when cutting it, so a cut can land on any frame rather than only on certain stored frames. |
| PySceneDetect | A free tool that finds the moments in a video where one shot cuts to the next, and returns their timestamps. |
| 1080p | A video picture 1920 pixels wide and 1080 pixels tall, the usual "full HD" size. |
| Bucket | A storage space for files at a hosting company, reached over the internet rather than from a disk in the server. |
| Presigned link | A web address that lets a browser upload or download one file directly from the bucket for a few minutes, without a password and without the file passing through our server. |

**Building and running**

| Term | Meaning |
|---|---|
| Railway | A hosting company that runs our code from the GitHub repository and gives it a public web address. |
| Volume | A disk attached to a server at Railway that keeps its files when the server restarts. |
| Dockerfile | A short recipe file that lists what to install (Python, ffmpeg) so the server is built the same way every time. |
| honcho | A small program that starts several programs together (here the web app and the worker) and stops them all if one dies, so the host restarts the lot. |
| SQLite | A database stored as one file on disk, run inside our own program rather than as a separate server. |
| HTMX | A small browser script that lets a page refresh one part of itself from the server (for example, a job's status every 5 seconds) without writing a separate front-end app. |
| HTTP basic auth | The browser's built-in password box. One shared word lets a visitor in; there are no user accounts. |
| Fake provider | A stand-in for an outside AI service, used in tests, that returns canned answers instantly and costs nothing. |
| moto | A library that pretends to be an S3 bucket inside tests, so tests never touch real storage. |

---

## 1. Language and web framework

| Option | Pros | Cons |
|---|---|---|
| **Python 3.13 + FastAPI** ✅ | Same language as the working clip scripts (`tools/gen_clip.py`); best libraries for images (Pillow), scene detection (PySceneDetect) and S3 (boto3); one builder knows one language (GC-2) | FastAPI is pre-1.0 and changes minor APIs between releases (current is 0.146, 2026-10-18 [verify]) |
| TypeScript + Next.js | One language for browser and server; large ecosystem | Image and scene-detection libraries are weaker; research code would be rewritten; a front-end build step to maintain before GC-1 |
| Python + Django | Admin screens and ORM included | Heavier than one user needs |

**Choice: Python 3.13 with FastAPI, exact versions pinned with uv.** The pipeline is images, video and HTTP calls to AI services, and Python already runs it end to end (§7). Python 3.13 gets security fixes until 2029 [verify].

**Needs from the design.** Routes that call SQLite or boto3 (both blocking) must not block the web server's event loop, or status pages stall while a job runs (I-5, ≤ 1 s).

## 2. Web client

| Option | Pros | Cons |
|---|---|---|
| **Jinja2 pages + HTMX 2 (file in the repo, 0BSD licence)** ✅ | No build step and no second codebase; status polling every 5 s is one attribute (FR-1.3, I-5); the editor (FR-1.13–1.16) is a shot list with a form per shot, which HTMX swaps in place; one builder, 3 days (GC-1, GC-2) | A drag-and-drop timeline would want a component framework; v1 needs none |
| React + Vite single-page app | Best for a drag-and-drop editor | A build, a router and an API client to write before the first screen works |

**Choice: Jinja2 + HTMX.** Every v1 screen (HLD §5 wireframe) is a form, a table or a video player; none needs client-side state. The "play both" button is a few lines of plain JavaScript.

## 3. Database and job queue

| Option | Pros | Cons |
|---|---|---|
| **SQLite (WAL mode) via SQLAlchemy 2.0** ✅ | No server to run or pay for; one file; fine for < 10,000 rows (HLD §5, SC-1) | App and worker must share one machine; parallel shot threads writing at once can hit "database is locked" |
| Railway Postgres | Survives moving the worker to its own service; the next step for SC-2 | A second service to pay for and run; nothing at this load needs it |
| Redis queue (RQ, Celery) | Standard job queue | A broker the HLD left out on purpose (HLD §5) |

**Choice: SQLite.** The job table is the queue, as the HLD decided, and one worker polls it. SQLAlchemy keeps the move to Postgres a connection-string change when SC-2's trigger is hit.

**Needs from the design.** App and worker share one SQLite file, so they run in one container. Writes from parallel shots must be short and wait on a lock rather than fail (a busy timeout of several seconds). A job left "running" by a crash or redeploy must be marked stopped with a reason on startup (RL-1, RL-2).

## 4. File storage

**Why it exists.** Photos, enhanced photos, clips, songs and videos: about 140 MB to 1 GB per job (HLD §2), too big for the database.

| Option | Pros | Cons |
|---|---|---|
| **Railway Storage Bucket** ✅ | S3-compatible with presigned links, which the HLD's direct upload and download need (HLD §4.1 `createUpload`, `getVideo`); $0.015/GB-month, so 55 GB is under $1/month [verify]; same provider as hosting (GC-4) | Bucket CORS must be set; no automatic expiry of old files; files the worker uploads count as billed egress (about $0.05/GB [verify]) |
| Railway volume (local disk) | Simplest code; no presigning | Capped at 5 GB on Hobby, below the typical 10 GB (HLD §2) [verify] |
| DigitalOcean Spaces | Approved provider; S3-compatible | $5/month minimum and a second provider account |

**Choice: Railway Storage Bucket.** It is the only approved option that holds the HLD's file sizes without a second account. Local development uses a separate dev bucket with localhost in its CORS list, so there is one code path.

**Needs from the design.** Uploads must refuse files over 25 MB at the bucket, not only in the page (DE-2). Download links must tell the browser to save the file, since a cross-site download link is otherwise ignored (FR-1.9). OpenRouter's clip links need our API key, so the worker downloads each clip and stores it itself, promptly, because OpenRouter keeps the clip until it is downloaded. The 55 GB worst case fits, so deleting photos is tidy-up, not a need.

## 5. Hosting

| Option | Pros | Cons |
|---|---|---|
| **Railway Hobby, one service from a Dockerfile (`python:3.13-slim-trixie`), honcho starting app + worker** ✅ | Approved (GC-4); deploys from GitHub; HTTPS and a public address included; about $6–8/month [verify]; trixie ships ffmpeg 7.1 (bookworm has 5.1) | 5 GB volume (SQLite only); a service with a volume has brief downtime on every redeploy, which kills a running job; Hobby terms say "personal projects", borderline for work shown to a company [verify] |
| Builder's machine only | $0; nothing to deploy | Demo depends on one laptop being on; nobody at AutoHDR can open it |
| DigitalOcean App Platform | Approved | Separate worker component billed separately; more setup for the same result |

**Choice: Railway Hobby, one service; honcho runs the app and the worker and exits if either dies, so Railway restarts the container.** One container is what SQLite needs (module 3). Without the supervisor a dead worker leaves a healthy-looking site whose jobs never move, and RL-1's 60 s report never fires.

**Needs from the design.** Temporary video files go on the container's own disk, not the 5 GB volume. Auto-deploy is frozen on demo day (DE-4).

## 6. Video generation

**Why it exists.** Turns each enhanced photo plus a camera-movement instruction into a clip (FR-1.4).

| Option | Pros | Cons |
|---|---|---|
| **OpenRouter Videos API, `google/veo-3.1`, 1080p, no audio, BYOK Google Cloud key** ✅ | Measured at 720p: 19 clips, 0 errors, 48–88 s each, stays closest to the photo (VIDEO_RESEARCH §7.4); 1080p costs the same (DE-5); OpenRouter serves it from Vertex AI's general-release model, retiring "Nov 17, 2026 or later", not the preview that shuts down 2026-10-22 [verify]; user prefers it | 4, 6 or 8 s and 24 fps only; added people and vents seen in bathroom shots (§7.2–7.3); OpenRouter reports $0 under BYOK, so the real cost sits on the Google Cloud bill; Google Cloud is not named on the approved list (§18) |
| `bytedance/seedance-2.0` through OpenRouter | Measured: 6 clips, 0 errors; any length 4–15 s; billed by OpenRouter, so cost is in the response (CO-1) | 173–270 s per clip; moves further from the photo and invents detail (§7.2); about $0.76 per 5 s at 720p and more at 1080p [verify] |
| `google/veo-3.1-lite` or `-fast` | $0.05–0.10/s at 1080p, 2–4× cheaper [verify] | Not tested on our photos |

**Choice: Veo 3.1 through OpenRouter, with the model id read from configuration so Seedance 2.0 can replace it without a code change.** It is the measured working choice; Seedance covers shots longer than 8 s and a Veo outage.

**Needs from the design.** Each style shot's movement prompt starts from the PRD's starter-kit prompt for its movement name (PRD pp.8–9); 1080p 16:9 is requested (DE-5). A job's shots are submitted in parallel: one after another, the worst case is about 59 min on Veo and the first pass alone is 25–35 min on Seedance, against PF-1's 30 min (§7.1). Each clip is requested at the next allowed length up from its cut and trimmed (VR-2). Photos are cropped to 16:9 first (§7.2). Under BYOK the call cost is recorded as clip seconds × the listed price, since the response says $0 (CO-1). OpenRouter's "out of budget" (402) and "rate limited" (429) answers become a shot's stop reason within 60 s (RL-1).

## 7. Photo enhancement

**Why it exists.** The PRD's creator takes "a mediocre photo" and changes "their composition, their lens, the angle they'd get … the lighting for the time of day" (PRD p.3); its worked example makes a close-up detail shot from a wide kitchen photo in two edits (pp.4–5). Each style shot stores that edit as a prompt (FR-1.8).

| Option | Pros | Cons |
|---|---|---|
| **Pillow crop and resize, then `google/gemini-nano-banana-2.1` with the style shot's photo-edit prompt** ✅ | The crop is required anyway (§7.2); the PRD's own example uses Nano Banana (pp.4–5), and its cinematic and detail-shot prompts (pp.10–12) each end "preserve all architectural and interior details"; about $0.04 per 1K image [verify] | Released 2026-10-06 and untested on our photos; a new angle can invent geometry (VR-5); only served through Google AI Studio, so it bills OpenRouter credits, not the BYOK key |
| Pillow only (crop, exposure, colour) | Cannot change a room (VR-5); free | Cannot change lens or angle, so FR-1.8 is not met |
| `google/gemini-3.1-flash-image` | Older, more used | About twice the price per image |
| `openai/gpt-5.4-image-2` | Strong editing | Several times the price per image; slower |

**Choice: Pillow crop always, then Nano Banana 2.1 running the style shot's photo-edit prompt, with `gemini-3.1-flash-image` as a configured fallback.** It is the model the PRD's example uses and the only option that meets FR-1.8 in full.

**Needs from the design.** The original photo is kept next to the edited one, and the quality check compares them for added or removed fixtures before the edit is used (VR-5). An edit that fails the check is retried, then falls back to the crop-only photo with the reason recorded. A style shot may chain more than one edit, as the PRD example does.

## 8. Quality check and cut detection

**Why it exists.** Flags visibly AI shots and changed rooms before delivery (FR-1.7, QC-1, VR-5), and measures a reproduction's cut times against the original (VR-2, FR-2.4).

| Option | Pros | Cons |
|---|---|---|
| **`google/gemini-3.8-flash` given the clip plus frames extracted at 4–8 per second; PySceneDetect 0.6.7.1 (headless OpenCV) for cut times** ✅ | Sees the whole clip and dense frames: a six-frame look missed a person in a mirror (§7.2), and the model samples video at about 1 frame per second by default [verify]; about $0.01 per check [verify]; a cut detector gives exact timestamps (VR-2 ±0.1 s) | Model judgement is unproven against the reviewer (QC-1 is [tbd]); the cut detector misses crossfades, so a transition the style says is a crossfade is checked against the style's own timing |
| Claude via the Anthropic API with extracted frames | Strong image reasoning; approved | Sees frames, not motion |
| `google/gemini-3.1-pro-preview` | Stronger reasoning | Preview model; slower and several times the price |

**Choice: Gemini 3.8 Flash for checking clips and edited photos; PySceneDetect for cut times in finished videos.** A language model is not reliable for timestamps to a tenth of a second; a cut detector is. PySceneDetect is pinned to 0.6.7.1 with headless OpenCV below 5.0 because the slim image has no graphics libraries.

**Needs from the design.** The check compares counts of people, vents and fixtures between the clip or edited photo and the source photo (VR-5).

## 9. Video assembly

**Choice: ffmpeg 7.1 from Debian trixie, called from the worker.** It trims each clip to its cut, joins them and lays the song; every Python video library calls ffmpeg underneath. Debian's build is GPL, which is fine because we run it, not redistribute it.

**Needs from the design.** Cuts are re-encoded, not copied, and converted from Veo's 24 fps to the original's frame rate, or cuts snap up to a second off (VR-2).

## 10. Songs

| Option | Pros | Cons |
|---|---|---|
| **Free Music Archive tracks under CC BY-NC or BY-NC-SA** ✅ | Licence and artist shown per track (GC-5); free | Each track's licence must be read; BY-NC-SA makes the finished video BY-NC-SA too |
| ccMixter | Same licence family | Smaller catalogue of upbeat tracks |
| Suno or other generated music | Made to length | Not on the approved list; licence terms are not CC (GC-4, GC-5) |

**Choice: Free Music Archive tracks under BY-NC or BY-NC-SA only.** Putting music under video counts as an adaptation, so "NoDerivatives" (ND) tracks are not allowed. The licence code, artist and source URL are stored per track, and the credit line appears on the video page (GC-5).

## 11. Access

| Option | Pros | Cons |
|---|---|---|
| **One shared passphrase via HTTP basic auth, set as an environment variable** ✅ | Stops anyone who finds the address from starting paid jobs on the user's bill (GC-3 sets no limit); no accounts, so FR-3.2 still holds; a few lines | One word shared by everyone; no per-person record |
| Open address (literal FR-3.2) | Nothing to build | Up to $52 per stranger's job with nothing stopping it |
| Private address only (never shared) | No code | AutoHDR cannot try it |

**Choice: one shared passphrase.** It reads FR-3.2 ("no accounts or logins") as "no accounts"; §18 asks for that reading to be confirmed.

## 12. Secrets

| Option | Pros | Cons |
|---|---|---|
| **Environment variables: Railway service variables; `.env` locally (gitignored, `.env.example` committed)** ✅ | Three secrets (OpenRouter key, bucket keys, passphrase); nothing extra to run | No rotation or audit; fine for a demo |
| A secrets manager (Doppler, 1Password) | Rotation, audit | Another account for three values |

**Choice: environment variables.** The Google Cloud key is stored only in OpenRouter's BYOK settings and never reaches our code. The repository is public, so photos, clips and `out/` stay gitignored.

## 13. Observability

**Choice: the job log tables (OB-1, OB-2, CO-1) plus Railway's stdout logs.** Every number in `KEY_METRICS.md` is a query over jobs, shots and attempts; a tracing or dashboard vendor would hold nothing those rows don't.

## 14. Testing

| Option | Pros | Cons |
|---|---|---|
| **pytest + FastAPI TestClient + fake providers + moto for the bucket; Playwright (Chromium) for screens; an eval script for EV-1 and EV-2** ✅ | Tests never spend money or wait minutes; failure injection for RL-1 to RL-3 is a fake that returns errors | Fakes can drift from the real APIs; a small live check before the demo covers that |
| Recorded real responses (VCR-style) | Closer to the real APIs | Video responses are large files; recordings go stale as models change |
| MinIO instead of moto | A real S3 server, so browser uploads run end to end | A second service in CI |

**Choice: pytest with fakes and moto, Playwright for screens, and a separate eval script that makes real calls only when run by hand.** The existing `tools/gen_clip.py` already uses the right request shape and is the reference for the real provider code.

## 15. CI/CD

| Option | Pros | Cons |
|---|---|---|
| **GitHub Actions (ruff, pytest, Playwright) + Railway deploy from the branch with "wait for CI"** ✅ | Repo is public, so Actions minutes are free [verify]; Railway deploys on push | One more workflow file |
| Railway deploy only, no CI | Nothing to set up | Broken builds reach the demo address |

**Choice: GitHub Actions for checks; Railway deploys only after CI passes.**

## 16. Go-live prerequisites

| Prerequisite | Lead time | Blocks |
|---|---|---|
| Decide the two Gate conflicts in §18 (Google Cloud billing under GC-4; passphrase vs FR-3.2) | Minutes, the user | Making the address public |
| OpenRouter: key spend limit with "include BYOK" on; credits for Nano Banana, Gemini and the Seedance fallback; Google Cloud budget alert on the BYOK project | Under an hour | Every job; protects against runaway cost (GC-3) |
| One Veo call on 2026-10-21 and on the demo day, to confirm the route still works [verify] | Minutes | Live demo (DE-4) |
| Railway Hobby account, one bucket per environment, bucket CORS for the app's address and localhost | Under an hour | Uploads and downloads (FR-1.1, FR-1.9) |
| Pick 2–3 BY-NC or BY-NC-SA demo songs, record licences, and make each demo style's original with that song (§18) | A few hours | Styles and reproductions (FR-2.2, VR-2) |
| Pre-generate the demo job and keep a copy offline (DE-4) | One job, about 10 min | The demo if live generation is slow |

## 17. Open choices

| Choice | Current lean | Settled by |
|---|---|---|
| Veo 3.1 vs Veo 3.1 Lite or Fast | Veo 3.1 | One clip on each cheaper tier on the same three photos (§7.2), judged by the reviewer |
| How far photo edits may move the angle | Full PRD edits, with crop-only fallback per shot | First 12 test videos: does the edit ever change a room (VR-5)? |
| Style as stored data or a trained model | Stored data (REQUIREMENTS Definitions: "a style is stored data, not a trained model") | Confirmed 2026-10-18; revisit only if reproductions miss VR-4 |
| Seedance fallback at 1080p or 720p | 1080p to meet DE-5 | Its 1080p price on the first fallback call |
| Quality-check score cut-off and frame rate | Unset (QC-1 is [tbd]); 4–8 frames per second | First 12 test videos against the reviewer's marks |

## 18. Open questions

The defaults below are best assumptions taken without a meeting. They are now written into `REQUIREMENTS.md` and `HIGH_LEVEL_DESIGN.md`, and the owner can overturn any of them.

| Kind | Issue | Decision applied |
|---|---|---|
| Requirements conflict (Gate) | BYOK makes Google Cloud (Vertex AI) bill the user's own project; the approved list names "Google One", not Google Cloud (GC-4) | GC-4: Google models through OpenRouter, BYOK included, count as OpenRouter use. If not allowed, turn BYOK off and pay through OpenRouter at the same list price |
| Requirements conflict | No logins (FR-3.2) on a public address with no spend limit (GC-3) lets anyone start paid jobs | FR-3.2: no accounts, one shared passphrase (module 11) |
| Requirements conflict | A reproduction must use the original's song (VR-2), but songs must be CC (GC-5); a real creator's video almost always has a commercial song | GC-5: each demo style's original is made by the builder with a BY-NC or BY-NC-SA track |
| Requirements conflict, resolved for the PRD | Changing angle and lens (FR-1.8) risks inventing geometry (VR-5) | FR-1.8 keeps composition, lens, angle and light as the PRD asks (pp.3–5); VR-5 is enforced by the check (module 7). If edits fail VR-5 too often, they narrow per shot and the narrowing is recorded |
| Requirements gap | Under BYOK, OpenRouter returns $0 for Veo (§7.1) | CO-1: BYOK calls record seconds × list price |
| Requirements gap | The 12 test shoots are real customer photos sent to OpenRouter, Google and ByteDance | GC-9: allowed for approved providers, never committed |
| Design change | Veo clips are 4, 6 or 8 s; a job's shots must run in parallel for PF-1 | HLD §2 and §4: shots run in parallel; clip length is the next allowed length up, trimmed at assembly |

---

## Sources (checked 2026-10-18)

- [OpenRouter models API](https://openrouter.ai/api/v1/models) and [videos models API](https://openrouter.ai/api/v1/videos/models): model ids, durations, frame inputs, per-second and per-token prices; `/models/{id}/endpoints` for `google/veo-3.1` (Vertex) and `google/gemini-nano-banana-2.1` (AI Studio only)
- [OpenRouter BYOK](https://openrouter.ai/docs/guides/overview/auth/byok) and [limits](https://openrouter.ai/docs/api/reference/limits): BYOK fee and allowance, `include_byok_in_limit`, 402 and 429 answers
- [Gemini API deprecations](https://ai.google.dev/gemini-api/docs/deprecations): Veo 3.1 preview shutdown 2026-10-22
- [Vertex AI Veo 3.1](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate): `veo-3.1-generate-001` general release, retirement "November 17, 2026 or later", 24 fps
- [Railway volumes](https://docs.railway.com/volumes/reference): Hobby volume 5 GB, no replicas with a volume
- [Railway Storage Buckets](https://docs.railway.com/storage-buckets) and [billing](https://docs.railway.com/storage-buckets/billing.md): S3 API, presigned URLs, $0.015/GB-month, no lifecycle rules
- [Railway terms](https://railway.com/legal/terms): Hobby use terms
- [Nano Banana 2.1 pricing](https://tokencost.app/blog/nano-banana-2-1-pricing): about $0.034–0.04 per 1K image
- PyPI: fastapi, scenedetect (0.6.7.1, 0.7.2), SQLAlchemy, opencv-python-headless; [Debian ffmpeg](https://sources.debian.org/src/ffmpeg/) (trixie 7.1, bookworm 5.1)
- [CC BY-NC-ND 4.0 legal code](https://creativecommons.org/licenses/by-nc-nd/4.0/legalcode): music synced to video is adapted material
- `VIDEO_RESEARCH.md` §7: measured clip times, costs and failures
