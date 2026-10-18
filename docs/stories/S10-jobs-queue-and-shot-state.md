### S10 — A submitted job waits its turn, and every shot's progress and every attempt is recorded

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — four routes and the worker's interface over `jobs`, `job_shots` and `attempts`
**Builds:** submitJob `POST /api/jobs/{id}/submit`; listJobs `GET /api/jobs`; getJob `GET /api/jobs/{id}`; getVideo `GET /api/jobs/{id}/video`; the `attempts` write path; the job and shot status write paths; Jobs interface claimNextJob, recoverInterrupted, setShotState, setShotPhoto, startAttempt, finishAttempt, setShotResult, finishJob, stopJob; the shot state rules; Jobs' Must holds and Failure behaviour; the measurement records `first_submitted_at`, `submitted_at`, `started_at`, `deadline_at`, `finished_at`, `first_finished_at`, `total_cost_usd`
**Extends:** the `jobs` and `job_shots` rows created by S09 (built against seeded synthetic rows)
**Stubs:** Files.presignDownload for the video and clips — removed by S22
**Requirements:** FR-1.3, FR-1.5, FR-1.7, FR-1.9, FR-1.11, SC-1, RL-2, QC-2, OB-1, OB-2, CO-1
**Guards:** SC-1, RL-1, RL-2, QC-2, PF-1

#### Why
The worker needs one safe place to take the next job and record every step, and the photographer needs to see where each shot is, why any failed and that a second job is waiting.

#### How it's checked
pytest against the routes and the interface with seeded drafts, including several threads calling the interface at once.

#### Acceptance criteria
1. Submitting queues the job
   Given a draft with a ready plan
   When `POST /api/jobs/{id}/submit` is sent
   Then the answer is 202 with status `queued` and first submit time set
2. A second job waits
   Given job A `running`
   When job B is submitted
   Then getJob for B shows `queued` with `waitingBehind` A
3. Only one job runs
   Given two queued jobs and two threads calling claimNextJob at once
   When both return
   Then exactly one gets a job and it is the oldest
4. The run budget is set at claim
   Given a queued job
   When claimNextJob takes it at 10:00
   Then its deadline is 10:30
5. A fifth attempt is refused
   Given a shot with 4 attempts in its current round
   When startAttempt is called
   Then it raises AttemptLimitReached
6. A failed shot always has a reason
   Given a shot in `checking`
   When setShotResult marks it failed with `flagged_every_attempt`
   Then getJob lists the shot with that reason and the last check's notes
7. Flagged clips never reach the page
   Given a shot whose attempt 1 was flagged and attempt 2 passed
   When getJob is called
   Then the shot's clip link is attempt 2's
8. Stopping keeps finished shots
   Given a running job with 3 passed shots and 2 generating
   When stopJob is called with `out_of_credit`
   Then the job is `stopped`, the 3 shots stay passed and the 2 are failed with `job_stopped`
9. Writes after a stop are refused
   Given a job that is `stopped`
   When setShotState is called for one of its shots
   Then it raises JobNotRunning
10. A worker restart stops the job
    Given a running job with one attempt `running`
    When recoverInterrupted runs
    Then the job is `stopped` with `worker_restarted` and the attempt is `error`
11. Finishing totals the cost
    Given a running job whose calls cost $1.20 and $0.40
    When finishJob marks it ready with a video
    Then the job is `ready`, its total cost is $1.60 and its first finish time is set
12. Ready is never early
    Given a running job with one shot still `generating`
    When finishJob is called with `ready`
    Then it is refused
13. Jobs list newest first
    Given three jobs made at 9:00, 10:00 and 11:00
    When `GET /api/jobs` is called
    Then they are listed 11:00, 10:00, 9:00 with status and elapsed time
14. Video links
    Given a ready job
    When `GET /api/jobs/{id}/video` is called
    Then it returns a play link, a download link and the duration
15. No video yet
    Given a queued job
    When `GET /api/jobs/{id}/video` is called
    Then the answer is 409 `no_video`
16. The prepared photo is recorded
    Given a shot in `editing`
    When setShotPhoto records crop only with the note "window changed"
    Then getJob shows the shot as crop only with that note

#### Not in this story
- Start again, redo and the editor's edits — picked up by S11
- The job page — picked up by S16
