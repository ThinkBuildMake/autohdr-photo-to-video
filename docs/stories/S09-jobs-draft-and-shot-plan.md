### S09 — Starting a video writes a shot plan from the style text that the photographer can change

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — three routes and the background planning job on two tables
**Builds:** the `jobs` insert path and the `job_shots` plan fields' write path; createJob `POST /api/jobs`; replanJob `POST /api/jobs/{id}/plan`; updateJobShots `PUT /api/jobs/{id}/shots`; the planJob background job, including planning again any job left `planning` on app start; the plan validation rules (movement names, lengths that fit the model's longest clip, total length within the song, photos in the shoot)
**Extends:** none
**Stubs:** Library.getStyle, Photoshoots.listPhotos, Providers.planShots and Providers.allowedLengths — removed by S21
**Requirements:** FR-1.2, FR-1.10, FR-2.3, FR-2.5, OB-1
**Guards:** CH-1, OB-1

#### Why
The style is text, so each job needs its own shot plan written from the text and the photos, and the photographer must be able to fix it before any money is spent.

#### How it's checked
pytest against the routes with a stub planner that answers fixed plans, valid and invalid.

#### Acceptance criteria
1. A draft is created and planned
   Given a ready shoot of 6 photos and the style text "Slow Dolly In through each room"
   When `POST /api/jobs` is sent with that text and a song
   Then the answer is 201 with status `draft` and plan `planning`
2. The plan arrives
   Given that draft and a stub plan of 6 shots
   When planning finishes
   Then `GET /api/jobs/{id}` shows plan `ready` with 6 shots in order, each with its plan note
3. A preset sets frame rate and song offset
   Given the preset "Golden hour" with fps 24 and song offset 12 s
   When a job is created with its id and its text
   Then the job has fps 24 and song offset 12 s
4. Missing rooms are noted
   Given the stub plan skips a shot because the text asks for a pool
   When planning finishes
   Then that shot has no photo and the job's plan notes mention the pool
5. An invalid plan is asked for again once
   Given the stub planner first answers an unknown movement and then a valid plan
   When planning runs
   Then the job's plan is the valid one
6. Two bad plans fail with a reason
   Given the stub planner answers an invalid plan twice
   When planning runs
   Then plan status is `failed` with the reason
7. The photographer edits the plan
   Given a draft with a ready plan of 6 shots
   When `PUT /api/jobs/{id}/shots` sends 5 shots with one movement changed to `crane_up`
   Then the job has 5 shots and the changed one shows `crane_up`
8. A bad edit names the shot
   Given the same draft
   When `PUT /api/jobs/{id}/shots` sends a shot with a 12 s length for a model whose longest clip is 8 s
   Then the answer is 400 `invalid_plan` naming that shot
9. Re-planning from new text
   Given a draft with a ready plan
   When `POST /api/jobs/{id}/plan` sends new style text
   Then plan status is `planning` and the job keeps the new text
10. The job keeps its own text
    Given a job created from the preset "Golden hour"
    When the preset's text is changed
    Then the job still shows the text it was planned from
11. A shoot still uploading is refused
    Given a shoot `awaiting_upload`
    When `POST /api/jobs` names it
    Then the answer is 409 `photoshoot_not_ready`
12. Interrupted planning restarts
    Given a job left `planning` when the app stopped
    When the app starts
    Then planning runs again for that job

#### Not in this story
- Submitting and the queue — picked up by S10
- The plan screen — picked up by S15
