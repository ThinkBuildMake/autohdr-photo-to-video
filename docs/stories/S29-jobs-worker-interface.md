### S29 — The worker can take the next job safely and record every shot and attempt

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — the worker's interface into Jobs and the shot state rules
**Builds:** the `attempts` write path; the job and shot status write paths; Jobs interface claimNextJob, recoverInterrupted, setShotState, setShotPhoto, startAttempt, finishAttempt, setShotResult, finishJob, stopJob; the shot state rules; Jobs' Must holds on attempts, failed shots and ready jobs; Jobs' Failure behaviour row "Worker restarted mid-job"; the measurement records `started_at`, `deadline_at`, `finished_at`, `first_finished_at`, `total_cost_usd`
**Extends:** the `jobs` and `job_shots` rows created by S09 (built against seeded synthetic rows)
**Stubs:** none beyond S01's
**Requirements:** RL-2, QC-2, OB-2, CO-1, SC-1
**Supports:** FR-1.5 (shown in S23)
**Guards:** SC-1, RL-1, RL-2, QC-2, PF-1, PF-3

#### Why
The worker runs many shots at once from several threads. It needs one safe place to take a job and write each step, so the page always shows the truth.

#### How it's checked
pytest against the interface with seeded jobs, including several threads calling it at once.

#### Acceptance criteria
1. Only one job runs
   Given two queued jobs and two threads calling claimNextJob at once
   When both return
   Then exactly one gets a job and it is the oldest
2. The run budget is set at claim
   Given a queued job
   When claimNextJob takes it at 10:00
   Then its deadline is 10:30
3. A fifth attempt is refused
   Given a shot with 4 attempts in its current round
   When startAttempt is called
   Then it raises AttemptLimitReached
4. A failed shot always has a reason
   Given a shot in `checking`
   When setShotResult marks it failed with `flagged_every_attempt`
   Then getJob lists the shot with that reason and the last check's notes
5. The prepared photo is recorded
   Given a shot in `editing`
   When setShotPhoto records crop only with the note "window changed"
   Then getJob shows the shot as crop only with that note
6. Stopping keeps finished shots
   Given a running job with 3 passed shots and 2 generating
   When stopJob is called with `out_of_credit`
   Then the job is `stopped`, the 3 shots stay passed and the 2 are failed with `job_stopped`
7. Writes after a stop are refused
   Given a job that is `stopped`
   When setShotState is called for one of its shots
   Then it raises JobNotRunning
8. A worker restart stops the job
   Given a running job with one attempt `running`
   When recoverInterrupted runs
   Then the job is `stopped` with `worker_restarted` and the attempt is `error`
9. Finishing totals the cost
   Given a running job whose calls cost $1.20 and $0.40
   When finishJob marks it ready with a video
   Then the job is `ready`, its total cost is $1.60 and its first finish time is set
10. Ready is never early
    Given a running job with one shot still `generating`
    When finishJob is called with `ready`
    Then it is refused
11. Each finished run is a new version
    Given a ready job at video version 1
    When finishJob records a re-exported video
    Then its version is 2 and its first finish time is unchanged
12. An attempt's result is recorded
    Given a running attempt
    When finishAttempt records it flagged with score 0.8 and cost $0.40
    Then getJob shows the attempt flagged with that score and cost

#### Not in this story
- Restart, redo and editor edits — picked up by S11
- The worker that calls this interface — picked up by S12, S28 and S30
