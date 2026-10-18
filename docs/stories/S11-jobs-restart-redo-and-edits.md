### S11 — A finished or stopped job can be started again, have one shot redone, or be edited and re-exported

**Kind:** module
**Blocked by:** S09, S10
**Review gate:** agents
**Size:** M — four routes that set shots back to pending
**Builds:** restartJob `POST /api/jobs/{id}/restart`; redoShot `POST /api/jobs/{id}/shots/{position}/redo`; editShot `PATCH /api/jobs/{id}/shots/{position}`; exportJob `POST /api/jobs/{id}/export`; the `removed`, `needs_new_clip` and `edited_at` write paths; each shot's pending change (new clip, re-cut only, none)
**Extends:** S10's shot state rules (passed or failed back to pending with round + 1); S09's plan validation, reused for editor edits
**Stubs:** none beyond S01's
**Requirements:** FR-1.5, FR-1.12, FR-1.13, FR-1.14, FR-1.15, FR-1.16, CH-1
**Guards:** CH-1, QC-2

#### Why
The photographer fixes a video without paying for shots that were already fine: start again after a stop, redo one shot, or edit shots and re-export.

#### How it's checked
pytest against the routes with seeded finished and stopped jobs.

#### Acceptance criteria
1. Start again keeps passed shots
   Given a stopped job with 3 passed and 2 failed shots
   When `POST /api/jobs/{id}/restart` is sent
   Then the job is `queued`, the 2 failed shots are `pending` in round 1 and the 3 passed shots are unchanged
2. Only stopped jobs restart
   Given a ready job
   When `POST /api/jobs/{id}/restart` is sent
   Then the answer is 409 `not_stopped`
3. Redo one shot
   Given a ready job of 6 shots
   When shot 4 is redone
   Then shot 4 is `pending` in a new round, the job is `queued` and shots 1–3 and 5–6 keep their clips
4. No redo while busy
   Given a queued job
   When a shot is redone
   Then the answer is 409 `job_busy`
5. Swap a room
   Given a ready job and another photo of the same shoot
   When `PATCH` shot 2 sets that photo
   Then shot 2 will get a new clip
6. Change a movement
   Given a ready job
   When `PATCH` shot 3 sets movement `slider_truck_left_to_right`
   Then shot 3 will get a new clip
7. Length or transition only re-cuts
   Given a ready job
   When `PATCH` shot 1 sets a length of 3.5 s
   Then shot 1 is re-cut only and keeps its clip
8. Remove and put back a room
   Given a ready job
   When shot 5 is marked removed and then unmarked
   Then shot 5 is back in the export plan unchanged
9. A bad edit names the field
   Given a ready job
   When `PATCH` sets a photo from another shoot
   Then the answer is 400 `invalid_edit` naming the photo
10. Re-export makes only what changed
    Given edits that need a new clip for shot 2 and a re-cut for shot 1
    When `POST /api/jobs/{id}/export` is sent
    Then only shot 2 is `pending` and the job is `queued`
11. Nothing to export
    Given a ready job with no edits since its last video
    When `POST /api/jobs/{id}/export` is sent
    Then the answer is 409 `nothing_to_export`
12. Untouched shots never change
    Given a re-export of a 6-shot job where only shot 2 was edited
    When the export is queued
    Then shots 1 and 3–6 keep the same final attempt

#### Not in this story
- Making the pending shots and the new video version — done by S12, joined in S23 and S24
- The editor screen — picked up by S17
