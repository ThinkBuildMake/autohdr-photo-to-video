### S10 — A submitted job waits its turn, and the photographer can list jobs and open their videos

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — four routes over `jobs`, `job_shots` and `attempts`
**Builds:** submitJob `POST /api/jobs/{id}/submit`; listJobs `GET /api/jobs`; getJob `GET /api/jobs/{id}`; getVideo `GET /api/jobs/{id}/video`; Jobs' Failure behaviour row "Submit while another job runs"; the measurement record `first_submitted_at` and `submitted_at`
**Extends:** the `jobs` and `job_shots` rows created by S09 (built against seeded synthetic rows)
**Stubs:** Files.presignDownload for the video and clips — removed by S22
**Requirements:** SC-1, OB-1
**Supports:** FR-1.3, FR-1.7, FR-1.9, FR-1.11 (shown in S22)
**Guards:** SC-1, RL-2

#### Why
The photographer submits, leaves, and comes back to a list of jobs and a video to play. A second job waits instead of being refused.

#### How it's checked
pytest against the routes with seeded drafts, running jobs and finished jobs.

#### Acceptance criteria
1. Submitting queues the job
   Given a draft with a ready plan
   When `POST /api/jobs/{id}/submit` is sent
   Then the answer is 202 with status `queued` and first submit time set
2. A second job waits
   Given job A `running`
   When job B is submitted
   Then getJob for B shows `queued` with `waitingBehind` A
3. A draft with nothing to make is refused
   Given a draft whose every shot is skipped
   When `POST /api/jobs/{id}/submit` is sent
   Then the answer is 409 `no_shots_to_make`
4. Flagged clips never reach the page
   Given a shot whose attempt 1 was flagged and attempt 2 passed
   When getJob is called
   Then the shot's clip link is attempt 2's
5. Jobs list newest first
   Given three jobs made at 9:00, 10:00 and 11:00
   When `GET /api/jobs` is called
   Then they are listed 11:00, 10:00, 9:00 with status and elapsed time
6. Video links
   Given a ready job
   When `GET /api/jobs/{id}/video` is called
   Then it returns a play link, a download link and the duration
7. No video yet
   Given a queued job
   When `GET /api/jobs/{id}/video` is called
   Then the answer is 409 `no_video`

#### Not in this story
- The worker's interface for claiming jobs and recording shots — picked up by S29
- The job page — picked up by S16
