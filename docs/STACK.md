# STACK.md — AutoHDR Photo-to-Video technology choices

**What this document is.** A comparison of candidate technologies for each module, and the choice for each. `REQUIREMENTS.md` defines what the system must do; requirement IDs (e.g. `PF-1`) appear here only as the reason a choice wins or loses. Which components exist and the load they carry are in `HIGH_LEVEL_DESIGN.md`; how the pieces fit together is designed in `ARCHITECTURE.md`.

**How the shortlist was built.** Each module's options were researched against `REQUIREMENTS.md`, `HIGH_LEVEL_DESIGN.md`, `USERS.md`, `KEY_METRICS.md` and the 25 measured clips in `VIDEO_RESEARCH.md` §7, with deciding facts verified on 2026-10-18. No review meeting is available, so each module takes the recommended option (candidate: "make your best assumptions and move forward"). A separate agent that hadn't seen the research then checked the chosen stack for conflicts; CHECK_RESULT

**Markers.** **[verify]** = an external fact checked on 2026-10-18 that should be re-confirmed before it's relied on. Go-live prerequisites, open choices and open questions are in the last sections.

---

## Summary

| # | Module | Choice | Main reason |
|---|---|---|---|
| 1 | Language and web framework | Python 3.13, FastAPI 0.136, uv | One language with the research scripts and ffmpeg (GC-2) |
| 2 | Web client | Server-rendered Jinja2 pages + HTMX 2 | No build step; polling built in (FR-1.3, GC-1) |
| 3 | Database and job queue | SQLite (WAL) via SQLAlchemy 2.0; job table is the queue | 1 job at a time, < 10,000 rows (SC-1, HLD §5) |
| 4 | File storage | Railway Storage Bucket (S3 API, presigned links) | Holds 10–55 GB; volume caps at 5 GB (HLD §2) |
| 5 | Hosting | Railway Hobby, one service, Dockerfile | Approved provider (GC-4); about $5/month |
| 6 | Video generation | OpenRouter Videos API, `google/veo-3.1`, 720p, no audio; fallback `bytedance/seedance-2.0` | Measured best fit (VIDEO_RESEARCH §7.4); PF-1 |
| 7 | Photo enhancement | Pillow crop to 16:9 + `google/gemini-nano-banana-2.1` | Crop fixes bars (§7.2); edit serves FR-1.8 |
| 8 | Quality check and reading a past video | `google/gemini-3.8-flash` (video input) + PySceneDetect for cut times | Watches the clip itself (QC-1); cuts to ±0.1 s (VR-2) |
| 9 | Video assembly | ffmpeg 7 | The only tool needed to cut to the song (FR-1.4) |
| 10 | Songs | CC BY-NC tracks from Free Music Archive | License recorded per track (GC-5) |
| 11 | Sign-in | None | No accounts (FR-3.2); see open questions |
| 12 | Secrets | Environment variables (Railway variables, `.env` locally) | Two secrets in total |
| 13 | Observability | Job log tables + platform stdout logs | OB-1, OB-2, CO-1 are rows, not dashboards |
| 14 | Testing | pytest + fake providers; Playwright; eval script | Paid calls never run in tests; EV-1, EV-2 |
| 15 | CI/CD | GitHub Actions + Railway deploy from GitHub | Free at this size |

**Cost (per job and per month; no limit is set, GC-3):**

| Item | Cost |
|---|---|
| Video, first pass: 8 shots × 4 s × $0.20/s (Veo 3.1 list price, no audio; billed by Google under BYOK) | $6.40 [verify] |
| Video, regenerations: up to 3 more attempts per shot (QC-2) | up to $19.20 more |
| Photo enhancement: 8 edits × about $0.034 (1K image) | about $0.27 [verify] |
| Quality check: up to 32 short video calls on Gemini 3.8 Flash | under $0.10 [verify] |
| Hosting: Railway Hobby (includes $5 of usage) + bucket at $0.015/GB-month × 10–55 GB | $5–6/month [verify] |
| **Typical job (first pass)** | **about $6.80** |
| **Worst case job (every shot regenerated 3 times)** | **about $26** — no limit is set; driven entirely by video seconds |
| **Project (under 50 jobs, HLD §2)** | **about $340 typical, $1,300 if every job were worst case**, plus about $20 hosting |

If a shot's cut is longer than 4 s, it needs a 6 s or 8 s clip, which raises that shot's cost by 50% or 100%. The fallback Seedance 2.0 measured $0.76 per 5 s clip (§7.1), about the same per shot.

---

## Glossary

`REQUIREMENTS.md` defines the product's own vocabulary — style, shot, visibly AI-generated shot, job, reproduction — and it isn't repeated here.

**AI services**

| Term | Meaning |
|---|---|
| OpenRouter | A company that resells many AI models behind one account and one key. We send it a request naming the model; it passes the request on and returns the result. |
| BYOK ("bring your own key") | An OpenRouter setting where the user stores their own key for a provider (here Google). Requests still go through OpenRouter, but the provider bills the user's own account directly. |
| Veo 3.1 | Google's model that turns a photo plus a written instruction into a short video clip of 4, 6 or 8 seconds. |
| Seedance 2.0 | ByteDance's model that does the same job, with clips of 4 to 15 seconds. |
| First frame | The photo given to the video model as the clip's opening picture, so the clip starts in the real room. |
| Nano Banana 2.1 | The nickname for Google's image-editing model: it takes a photo and an instruction and returns an edited photo. |
| Gemini 3.8 Flash | A fast Google model that can watch a video and a photo and answer questions about them in text, such as "does a person appear?" |
| Preview model | A version a provider offers before it is final. Providers can switch preview versions off on a set date. |

**Video and files**

| Term | Meaning |
|---|---|
| ffmpeg | A free command-line program that cuts, joins and re-encodes video and audio files. |
| PySceneDetect | A free tool that finds the moments in a video where one shot cuts to the next, and returns their timestamps. |
| 720p | A video picture 1280 pixels wide and 720 pixels tall. |
| Bucket | A storage space for files at a hosting company, reached over the internet rather than from a disk in the server. |
| Presigned link | A web address that lets a browser upload or download one file directly from the bucket for a few minutes, without a password and without the file passing through our server. |

**Building and running**

| Term | Meaning |
|---|---|
| Railway | A hosting company that runs our code from the GitHub repository and gives it a public web address. |
| Volume | A disk attached to a server at Railway that keeps its files when the server restarts. |
| Dockerfile | A short recipe file that lists what to install (Python, ffmpeg) so the server is built the same way every time. |
| SQLite | A database stored as one file on disk, run inside our own program rather than as a separate server. |
| HTMX | A small browser script that lets a page refresh one part of itself from the server (for example, a job's status every 5 seconds) without writing a separate front-end app. |
| Fake provider | A stand-in for an outside AI service, used in tests, that returns canned answers instantly and costs nothing. |

---

## 1. Language and web framework

| Option | Pros | Cons |
|---|---|---|
| **Python 3.13 + FastAPI 0.136** ✅ | Same language as the working clip scripts (`tools/gen_clip.py`); best libraries for images (Pillow), scene detection (PySceneDetect) and S3 (boto3); one builder knows one language (GC-2) | Two languages if the client ever needs a rich front-end app; FastAPI is pre-1.0 and changes minor APIs between releases |
| TypeScript + Next.js | One language for browser and server; large ecosystem | Image and scene-detection libraries are weaker; research code would be rewritten; a front-end build step to maintain before GC-1 |
| Python + Django | Admin screens and ORM included | Heavier than one user needs; sync-first, while the worker spends its time waiting on outside services |

**Choice: Python 3.13 with FastAPI 0.136, packages pinned with uv.** The pipeline is images, video and HTTP calls to AI services, and Python already runs it end to end (§7). Python 3.13 gets security fixes until 2029 [verify].

## 2. Web client

| Option | Pros | Cons |
|---|---|---|
| **Jinja2 pages + HTMX 2 (file in the repo)** ✅ | No build step and no second codebase; status polling every 5 s is one attribute (FR-1.3, I-5); one builder, 3 days (GC-1, GC-2) | Richer editing later (UC-3 web editor) would want a component framework |
| React + Vite single-page app | Best for the later editor; large component ecosystem | A build, a router and an API client to write before the first screen works |

**Choice: Jinja2 + HTMX.** Every v1 screen (HLD §5 wireframe) is a form, a table or a video player; none needs client-side state. The "play both" button is a few lines of plain JavaScript.

## 3. Database and job queue

| Option | Pros | Cons |
|---|---|---|
| **SQLite (WAL mode) via SQLAlchemy 2.0** ✅ | No server to run or pay for; one file; fine for < 10,000 rows and one writer at a time (HLD §5, SC-1) | App and worker must run on the same machine; must be replaced for several workers on several machines (HLD §5 "What to add next") |
| Railway Postgres | Survives moving the worker to its own service; the next step for SC-2 | A second service to pay for and run; nothing at this load needs it |
| Redis queue (RQ, Celery) | Standard job queue | A broker the HLD left out on purpose (HLD §5 background worker) |

**Choice: SQLite.** The job table is the queue, as the HLD decided, and one worker polls it. SQLAlchemy keeps the move to Postgres a connection-string change when SC-2's trigger is hit.

**Needs from the design.** App server and worker share one SQLite file, so they run in the same container; a job claimed by the worker must not be claimed twice after a restart (SC-1).

## 4. File storage

**Why it exists.** Photos, enhanced photos, clips, songs and videos: about 140 MB to 1 GB per job (HLD §2), too big for the database.

| Option | Pros | Cons |
|---|---|---|
| **Railway Storage Bucket** ✅ | S3-compatible with presigned links, which the HLD's direct upload and download need (HLD §4.1 `createUpload`, `getVideo`); $0.015/GB-month, egress free [verify]; same provider as hosting (GC-4) | Bucket CORS must be set for browser uploads; public buckets not supported, so every file goes through a presigned link |
| Railway volume (local disk) | Simplest code; no presigning | Capped at 5 GB on Hobby, below the typical 10 GB (HLD §2) [verify] |
| DigitalOcean Spaces | Approved provider; S3-compatible | $5/month minimum and a second provider account |

**Choice: Railway Storage Bucket.** It is the only approved option that holds the HLD's file sizes without a second account. Local development uses a separate dev bucket, so there is one code path.

**Needs from the design.** The worst case (55 GB) still fits the bucket, so the HLD's "delete source photos after the demo" assumption is not needed for space; it can stay as tidy-up.

## 5. Hosting

| Option | Pros | Cons |
|---|---|---|
| **Railway Hobby, one service from a Dockerfile** ✅ | Approved (GC-4); deploys from GitHub; HTTPS and a public address included; about $5/month [verify]; Dockerfile installs ffmpeg | 5 GB volume cap (only SQLite lives there); one service means app and worker restart together |
| Builder's machine only | $0; nothing to deploy | Demo depends on one laptop being on; nobody at AutoHDR can open it (DE-4 rehearsal) |
| DigitalOcean App Platform | Approved | Separate worker component billed separately; more setup for the same result |

**Choice: Railway Hobby, one service running both the app process and the worker process.** One container is what SQLite needs (module 3), and the build runs the same locally (DE-3).

## 6. Video generation

**Why it exists.** Turns each enhanced photo plus a camera-movement instruction into a clip (FR-1.4).

| Option | Pros | Cons |
|---|---|---|
| **OpenRouter Videos API, `google/veo-3.1`, 720p, no audio, BYOK** ✅ | Measured: 19 clips, 0 errors, 48–88 s each, stays closest to the photo (VIDEO_RESEARCH §7.4); PF-1 met with parallel shots; user prefers it | 4, 6 or 8 s only; Google's preview Veo 3.1 is listed to shut down 2026-10-22, the day after GC-1 [verify, see §16]; added people and vents seen in bathroom shots (§7.2–7.3); real cost sits on the Google bill |
| `bytedance/seedance-2.0` through OpenRouter | Measured: 6 clips, 0 errors; any length 4–15 s; billed by OpenRouter so cost is in the response (CO-1) | 173–270 s per clip; moves further from the photo and invents detail (§7.2); about $0.76 per 5 s |
| `google/veo-3.1-lite` or `-fast` | $0.03–0.08/s, 4–7× cheaper [verify] | Not tested on our photos; same shutdown risk |

**Choice: Veo 3.1 through OpenRouter, with the model id read from configuration so Seedance 2.0 can replace it without a code change.** It is the measured working choice; the shutdown date makes the fallback a requirement, not a nicety.

**Needs from the design.** Clips come in fixed lengths, so each clip is generated at the next length up from its cut and trimmed (FR-1.4, VR-2). Shots of one job are submitted in parallel; sequential Seedance would miss PF-1 (§7.1). Photos are cropped to 16:9 before submission (§7.2).

## 7. Photo enhancement

| Option | Pros | Cons |
|---|---|---|
| **Pillow crop and resize, then `google/gemini-nano-banana-2.1`** ✅ | The crop is required anyway (§7.2); the edit can change light and framing toward the style (FR-1.8); about $0.034 per 1K image [verify] | A generative edit can add or remove fixtures (VR-5); untested on our photos |
| Pillow only (crop, exposure, colour) | Cannot change a room (VR-5); free | Cannot change angle or lens (FR-1.8 not fully met) |
| `openai/gpt-5.4-image-2` | Strong editing | Several times the price per image; slower |

**Choice: Pillow crop always, then Nano Banana 2.1 for the light-and-framing edit.** FR-1.8 asks for more than a crop; the quality check (module 8) compares the edited photo with the original so a changed room is caught.

**Needs from the design.** The original photo must be kept next to the edited one so the check and the reviewer can compare them (VR-5), and a shot must be able to fall back to the crop-only photo.

## 8. Quality check and reading a past video

**Why it exists.** Flags visibly AI shots before delivery (FR-1.7, QC-1), and turns a creator's past video into style shots (FR-2.1).

| Option | Pros | Cons |
|---|---|---|
| **`google/gemini-3.8-flash` (watches video) + PySceneDetect (cut times)** ✅ | Takes the whole clip, not a few frames, which matters because a six-frame look missed a person (§7.2); about a cent per check [verify]; scene detection gives exact cut timestamps (VR-2 ±0.1 s) | Model judgement is unproven against the reviewer (QC-1 is [tbd]) |
| Claude via the Anthropic API with extracted frames | Strong image reasoning; approved | Sees frames, not motion; the frame approach already missed a figure |
| `google/gemini-3.1-pro-preview` | Stronger reasoning | Preview model; slower and several times the price |

**Choice: Gemini 3.8 Flash for watching clips and labelling movements; PySceneDetect for cut times.** A language model is not reliable for timestamps to a tenth of a second; a cut detector is.

## 9. Video assembly

**Choice: ffmpeg 7 (the Debian package), called from the worker.** It trims each clip to its cut, joins them and lays the song; nothing else in the stack does that, and every Python video library calls ffmpeg underneath.

## 10. Songs

| Option | Pros | Cons |
|---|---|---|
| **Free Music Archive (CC BY-NC tracks)** ✅ | Licence and artist shown per track (GC-5); free | Catalogue varies; each track's licence must be read |
| ccMixter | Same licence family | Smaller catalogue of upbeat tracks |
| Suno or other generated music | Made to length | Not on the approved list; licence terms are not CC (GC-4, GC-5) |

**Choice: Free Music Archive tracks under CC BY-NC, stored in the bucket with title, artist, licence and source URL (GC-5).**

## 11. Sign-in

**Choice: none.** FR-3.2 rules out accounts. The public address plus paid calls is a conflict; see open questions.

## 12. Secrets

| Option | Pros | Cons |
|---|---|---|
| **Environment variables: Railway service variables; `.env` locally (gitignored, `.env.example` committed)** ✅ | Two secrets (OpenRouter key, bucket keys); nothing extra to run | No rotation or audit; fine for a demo |
| A secrets manager (Doppler, 1Password) | Rotation, audit | Another account for two values |

**Choice: environment variables.** The Google key is stored only in OpenRouter's BYOK settings and never reaches our code.

## 13. Observability

**Choice: the job log tables (OB-1, OB-2, CO-1) plus Railway's stdout logs.** Every number in `KEY_METRICS.md` is a query over jobs, shots and attempts; a tracing or dashboard vendor would hold nothing those rows don't.

## 14. Testing

| Option | Pros | Cons |
|---|---|---|
| **pytest + FastAPI TestClient + fake providers; Playwright (Chromium) for screens; an eval script for EV-1 and EV-2** ✅ | Tests never spend money or wait minutes; failure injection for RL-1 to RL-3 is a fake that returns errors | Fakes can drift from the real APIs; a small live check before the demo covers that |
| Recorded real responses (VCR-style) | Closer to the real APIs | Video responses are large files; recordings go stale as models change |

**Choice: pytest with fakes, Playwright for screens, and a separate eval script that makes real calls only when run by hand.**

## 15. CI/CD

| Option | Pros | Cons |
|---|---|---|
| **GitHub Actions (ruff, pytest, Playwright) + Railway deploy from the branch** ✅ | Repo is already on GitHub; free minutes cover this size [verify]; Railway deploys on push | Deploy is not gated on CI unless Railway's "wait for CI" is turned on |
| Railway deploy only, no CI | Nothing to set up | Broken builds reach the demo address |

**Choice: GitHub Actions for checks, Railway's GitHub deploy with "wait for CI" on.**

## 16. Go-live prerequisites

| Prerequisite | Lead time | Blocks |
|---|---|---|
| Confirm which Google model OpenRouter's `google/veo-3.1` calls, and that it works after 2026-10-22; otherwise switch `VIDEO_MODEL` to Seedance 2.0 before showing the product after that date | Minutes (one call on 2026-10-22) | Any run after 2026-10-21 |
| Railway Hobby account, one bucket per environment, bucket CORS for the app's address | Under an hour | Uploads and downloads (FR-1.1, FR-1.9) |
| OpenRouter: BYOK Google key set, enough credit for Seedance fallback and Gemini calls | Minutes | Every job |
| Pick 2–3 demo songs and record their licences (GC-5) | An hour | Styles (FR-2.2) |
| Pre-generate the demo job (DE-4) | One job, about 10 min | The demo if live generation is slow |

## 17. Open choices

| Choice | Current lean | Settled by |
|---|---|---|
| Veo 3.1 vs Veo 3.1 Lite or Fast | Veo 3.1 | One clip on each cheaper tier on the same three photos (§7.2), judged by the reviewer |
| Nano Banana edit on or off by default | On, with crop-only fallback | First 12 test videos: does the edit ever change a room (VR-5)? |
| Quality-check score cut-off | Unset (QC-1 is [tbd]) | First 12 test videos against the reviewer's marks |

## 18. Open questions

| Kind | Issue | Proposed change |
|---|---|---|
| Requirements conflict | No sign-in (FR-3.2) on a public address means anyone with the link can start paid jobs; no spend limit (GC-3) means nothing stops them | Add a single shared access code for the demo (not an account), or keep the address private; amend FR-3.2 |
| Requirements conflict | BYOK makes Google bill the user's own account; the approved list names "Google One", not Google Cloud or AI Studio (GC-4) | Confirm BYOK Google counts as approved, or turn BYOK off so OpenRouter (approved) bills it; record in GC-4 |
| Requirements gap | Veo cost under BYOK does not come back in OpenRouter's response (§7.1), so CO-1 can only record the list price for Veo | Let CO-1 accept "list price × seconds" for BYOK calls |
| Design change | Veo clips are 4, 6 or 8 s; the HLD assumes clips match cut lengths | Add to HLD §4.3 `generateClip`: clip length is the next allowed length up, trimmed at assembly |

---

## Sources (checked 2026-10-18)

- [OpenRouter models API](https://openrouter.ai/api/v1/models) and [videos models API](https://openrouter.ai/api/v1/videos/models): model ids, durations, frame inputs, per-second and per-token prices
- [Gemini API deprecations](https://ai.google.dev/gemini-api/docs/deprecations): Veo 3.1 preview shutdown 2026-10-22 (snapshots disagree)
- [OpenRouter Veo 3.1 API page](https://openrouter.ai/google/veo-3.1/api): video generation listed as alpha
- [Railway volumes reference](https://docs.railway.com/volumes/reference): Hobby volume 5 GB
- [Railway Storage Buckets](https://docs.railway.com/storage-buckets) and [billing](https://docs.railway.com/storage-buckets/billing.md): S3 API, presigned URLs, $0.015/GB-month, free egress
- [Nano Banana 2.1 pricing](https://tokencost.app/blog/nano-banana-2-1-pricing): about $0.034 per 1K image
- [FastAPI 0.136.1 package listing](https://simple-repository.app.cern.ch/project/fastapi): Python 3.10–3.14
- `VIDEO_RESEARCH.md` §7: measured clip times, costs and failures
