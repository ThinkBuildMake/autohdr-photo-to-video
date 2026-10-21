# autohdr-photo-to-video

A web app that turns a real-estate photoshoot into a short walkthrough video set to music. The photographer picks a written style (or writes one), uploads the photos and checks the shot plan the system writes. A background worker then edits each photo, generates a clip from it, checks the clip for anything that looks AI-made or changes the room, regenerates flagged clips, and cuts the clips to the song. A style can be reproduced on another photoshoot and compared side by side with its reference video.

The brief is `docs/AutoHDR Photo to Video.pdf`. The design documents are in `docs/` (see [Documents](#documents)).

## Set up and run locally

This runs the app and the worker on your machine with fake AI providers, so nothing is spent and no API key is needed.

**You need:** macOS or Linux, `git`, [uv](https://docs.astral.sh/uv/getting-started/installation/) (it installs Python 3.13 for you), and `ffmpeg` on your `PATH` (`brew install ffmpeg` or `apt-get install ffmpeg`; jobs use it to cut video).

From the root of a fresh clone:

```bash
uv sync
FAKE_PROVIDERS=1 DEMO_PASSPHRASE=local-demo PORT=8000 uv run honcho start
```

`honcho` starts the two processes in `Procfile`: `web` (the app server on port 8000) and `worker` (runs queued jobs). If either stops, both stop. Press Ctrl+C to stop them.

Check it in a second terminal:

```
curl -i http://localhost:8000/healthz
```

It answers `HTTP/1.1 200 OK` with `{"status":"ok"}`. Then open <http://localhost:8000> in Chrome. The browser asks for a user name and password: any user name, password `local-demo` (the `DEMO_PASSPHRASE` you set). Every page except `/healthz` answers 401 without it, and refuses everyone when `DEMO_PASSPHRASE` is empty.

Notes:
- The database is a SQLite file at `./data/app.db`, created on first start (`data/` is git-ignored). Delete it to start fresh.
- `honcho` also reads a `.env` file in the repo root if there is one, and its values win over the ones on the command line. A fresh clone has none. If you have one, put `FAKE_PROVIDERS=1` and `DEMO_PASSPHRASE=...` in it instead.
- `PORT=8000` matters on macOS: without it `honcho` uses port 5000, which the AirPlay receiver holds. If something else already listens on 8000 (check with `lsof -i :8000`), pick another port and use it in the URLs below.
- With fake providers the pages, the API and the worker run, but uploading photos still needs a storage bucket (next section): there is no fake bucket.

### With real providers and storage

```bash
cp .env.example .env
```

Fill in `.env` (it is git-ignored; never commit it):
- `OPENROUTER_API_KEY`: an OpenRouter key. All video, photo-edit, vision and planning calls go through OpenRouter.
- `BUCKET_NAME`, `BUCKET_ACCESS_KEY_ID`, `BUCKET_SECRET_ACCESS_KEY` (and `BUCKET_ENDPOINT`, `BUCKET_REGION` if they differ): an S3-compatible bucket, a Railway Storage Bucket in production.
- `DEMO_PASSPHRASE`: the shared passphrase.
- `FAKE_PROVIDERS=0`.

The model settings in `.env.example` are the defaults; each comment says what it controls. Then run `uv run honcho start` (with `PORT=8000` in front on macOS).

Other commands:
- `uv run python -m app.library.seed --manifest PATH`: add Creative Commons songs from a JSON manifest (the format is in `app/library/seed.py`).
- `uv run python -m app.metrics [--sheet SHEET]`: print the key metrics from the job tables, or only for the jobs on a reviewer sheet.
- `uv run python -m app.evals import|run|links|report|all`: the evaluation runs on the test photoshoots (`--help` for the options).

### Tests

```bash
uv run playwright install chromium
env -u OPENROUTER_API_KEY FAKE_PROVIDERS=1 bash scripts/gate.sh
```

The gate (`scripts/gate.sh`) runs `uv sync --locked`, `ruff check`, `ruff format --check` and the whole pytest suite, Playwright browser tests included. It never calls an outside service. CI (`.github/workflows/ci.yml`) runs the same steps and also builds the Docker image and checks `/healthz`.

### Deploy

Production is one Railway service built from the `Dockerfile` (`railway.json`); the container runs `honcho start`, so the app and the worker share it. It needs a volume mounted at `/data` (`DATABASE_PATH=/data/app.db` is the image's default), a Railway Storage Bucket, and the variables above set on the service. Railway checks `/healthz` before switching traffic.

Demo day: [`docs/DEMO.md`](docs/DEMO.md) is the written script (redeploy, live clip check, live flow, the offline demo video, the deploy freeze).

## Design

Two processes of one Python codebase run in one container: the **app server** (FastAPI, pages rendered with Jinja2 and HTMX) and the **background worker**. They share one database, the `jobs` table is the queue, and one job runs at a time (SC-1). The browser sends photos to and fetches videos from the bucket directly through presigned links, so the app server never carries video.

Modules (each owns its tables; only Jobs writes job state):

| Module | What it does |
|---|---|
| Access | Checks the shared passphrase on every request except `/healthz` |
| Library | Songs and preset styles (a style is a text plus a song) |
| Photoshoots | Uploads and room labels for the photos |
| Jobs | A job's life: draft, the shot plan written from the style text, queue, shots, attempts, the finished video, and the editor's edits |
| Pipeline | Worker only: runs the next queued job, every shot in parallel within a 30 min budget, then cuts the clips to the song |
| Providers | Every call to an outside AI service, with its cost recorded |
| Media | Image and video processing: crop, frames, assemble, detect cuts |
| Files | Bucket key layout, presigned links, object reads and writes |
| Comparison | Cut times measured in finished videos; reference video against reproduction |
| Evals | Command line: runs the evaluations on the test photoshoots and writes their reports |

Outside services:
- **SQLite on Railway volume**: the database (SQLAlchemy, WAL mode).
- **Railway Storage Bucket**: photos, edited photos, clips, videos and songs (S3 API).
- **OpenRouter Videos API**: makes a clip from an edited photo as its first frame, with a fallback video model.
- **OpenRouter chat API**: edits photos, labels rooms, writes the shot plan and checks each clip and edit.

The contracts (schema, API, module interfaces, data flows) are in `docs/ARCHITECTURE.md`; why each part exists and how it is sized is `docs/HIGH_LEVEL_DESIGN.md`; the product choices are `docs/STACK.md`.

## Scaling

The demo is sized for one job at a time; scaling is written down, not built. [`docs/SCALING.md`](docs/SCALING.md) says what changes to run N jobs at once with each job still inside 30 minutes and its output unchanged: several workers claiming jobs from a server database, a shared cap on calls to the outside services, and a higher rate-limit tier there. Each piece has the measurable trigger that justifies adding it.

## Results on the 12 test shoots

**Status: no paid run has been recorded yet, so there are no numbers here.** The tables below replace this text only when `report --readme` is run on a fully reviewed sheet from a real run. Nothing here comes from the fake providers.

How to get the numbers. The real run makes about 20 paid videos (12 for EV-1, 2 per preset for EV-2), so it spends money and needs the owner's go-ahead first. The test photos stay outside the repo (they are never committed), for example in `../test-shoots`.

1. Run everything with one command: `python -m app.evals all --folder ../test-shoots --yes`. Without `--yes` it only prints what it would spend and exits 1. It imports the 12 shoots, runs EV-1 on the first preset, runs EV-2 for each style that has a reference video, and prints each sheet path.
2. Watch every video and fill the sheet's marks. The video links expire after 1 hour; `python -m app.evals links --sheet SHEET` writes the sheet again with fresh links.
3. Check the numbers with `python -m app.evals report --sheet SHEET [--sheet SHEET2 ...]`. It exits 2 and lists any delivered shot that is still unreviewed.
4. Put them here with `python -m app.evals report --sheet SHEET [--sheet SHEET2 ...] --readme README.md`. It replaces only this section, and only when every delivered shot is reviewed.
5. `python -m app.metrics --sheet SHEET` shows the typical wait over just the sheet's jobs.

Reports are written beside the sheet under `evals/`, which git ignores because the sheets hold signed links.

What the numbers mean:
- EV-1: one video per test shoot in one style, with job time (PF-1) and the typical wait (PF-2).
- EV-2: each preset reproduced on 2 shoots other than its demo shoot, judged against its reference video.
- VR-1 to VR-5: per video the visibly AI shots and rooms changed, the movement and transition matches, the worst cut error, and per style whether the plan followed its text and the reproduction looks like the reference.
- QC-1: how many reviewer-failed shots the automatic check had flagged (the catch rate).

## Documents

- `docs/AutoHDR Photo to Video.pdf`: the brief (wins where the documents disagree).
- `docs/USERS.md`, `docs/REQUIREMENTS.md`, `docs/KEY_METRICS.md`: who it is for, what it must do, how success is measured.
- `docs/HIGH_LEVEL_DESIGN.md`, `docs/ARCHITECTURE.md`, `docs/STACK.md`, `docs/SCALING.md`: the design.
- `docs/VIDEO_RESEARCH.md`: measurements of the video services.
- `docs/stories/`: the build plan; `docs/dev-log/`: what each story built and decided.
