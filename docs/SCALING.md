# SCALING.md — How the system would serve more than one user at a time

**What this document is.** The written scaling explanation GC-7 asks for, checked against SC-2: what changes to run N jobs at once, with each job still inside PF-1 and its outputs unchanged. Nothing here is built; the demo runs one job at a time (SC-1). The pieces and their triggers come from `HIGH_LEVEL_DESIGN.md` §5 "What to add next"; the contracts they touch are in `ARCHITECTURE.md`.

## Today: one job at a time

- One container runs the app server and one background worker (honcho), sharing one SQLite file on a Railway volume (STACK §3, §5).
- The `jobs` table is the queue. `claimNextJob` takes the oldest queued job only when no job is `running`, and a partial unique index allows at most one `running` row (ARCHITECTURE, Key decisions). A second job waits and its page says so.
- Inside a job, all shots run in parallel (up to `SHOTS_IN_FLIGHT`, default 8), so a job takes about 10 min on the median and at most 30 min (HLD §2). The 30 min budget starts when the worker claims the job (`jobs.deadline_at`, assumption A-7).
- Load is under 1 browser request per second with more than 100× headroom. Provider rate limits and per-second price are the real ceiling, not our servers (HLD §2).

## Running N jobs at once

Each job keeps the 30 min limit of PF-1 (`jobs.first_finished_at − jobs.first_submitted_at`), and its outputs stay the same: the same style text, shot plan, photo edits, prompts, quality checks, attempt limits (QC-2) and cuts to the song. Nothing in a job's path depends on how many other jobs run; only who claims it and how many calls share the providers change. A job left queued can miss PF-1 even when generation stays inside 30 min. The claim-time budget is PF-3 (`jobs.deadline_at` = `started_at` + 30 min); waiting is not taken from that budget.

What changes:

1. **Several workers claim jobs.** The rule "no job `running`" becomes "a job is claimed by exactly one worker": drop the partial unique index, and claim with a single conditional update (`status = 'queued'` → `running`, with the worker's id). On Postgres that is `SELECT … FOR UPDATE SKIP LOCKED`. Each worker runs one job, so N workers give N jobs at once.
2. **The database moves to a server database.** SQLite is one file that only one container can open, so workers on other machines cannot share it. STACK §3 keeps the move to Postgres a connection-string change through SQLAlchemy. The bucket is already shared (Railway Storage Bucket) and the app server keeps no state, so neither changes.
3. **Startup recovery becomes per worker.** Today a restarting worker marks every `running` job stopped. With N workers it must stop only the jobs it claimed (or those whose worker stopped sending a heartbeat), so one restart does not stop the others.
4. **Calls to the outside services are budgeted across jobs.** N jobs put up to 8 × N clips in flight. The providers' per-account limits are shared, so a limit hit by one job slows all of them. A shared counter in the database caps clips in flight across workers, and a worker only claims a job when the cap leaves room for its shots; otherwise the job stays queued, and that wait still counts toward PF-1.
5. **Cost grows linearly.** About $7 per job typical, up to $26–52 worst case (HLD §6), recorded per job (CO-1). N jobs at once cost N times as much per hour; no unit price changes.

What does not change: the module boundaries, the API, the screens, the pipeline steps and the checks. Only Jobs (claiming), the worker's recovery and Providers (the shared cap) change inside the code.

## Real queue and several workers

- **What breaks first:** one worker runs one job at a time; the second job waits for the first, up to 30 min.
- **Add when:** "Jobs waiting more than 5 min on the median, or a requirement for more than 1 job at once (SC-1 raised)".
- **What it is:** steps 1–3 above. The queue can stay a table on Postgres; a separate broker is only worth it when workers poll often enough to load the database, far beyond this load.
- **How the trigger is measured:** a job that has not started (`started_at` is null) has waited now − `jobs.submitted_at`. After a worker claims it, the wait is `jobs.started_at − jobs.submitted_at`.

## Higher rate-limit tier at the outside services

- **What breaks first:** per-account rate limits slow or stop jobs.
- **Add when:** "More than 1 job in 10 stops or slows past PF-1 on a limit".
- **What it is:** a paid or higher tier at the video, photo-edit and quality-check services (through OpenRouter, or the provider's own account under BYOK), plus step 4's shared cap set to the new limit.
- **How the trigger is measured:** every outside call writes a `provider_calls` row with its error kind (`rate_limited` for a limit), and every job records its status and times, so the share of jobs that stopped or ran past 30 min with a `rate_limited` call is one query.
