### S13 — Each finished video's cuts are measured, and a reproduction can be compared with its style's reference video

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — two routes, one interface and one table
**Builds:** the `cut_checks` write path; Comparison interface recordCuts; setReference `POST /api/styles/{id}/reference`; getReproduction `GET /api/styles/{id}/reproductions/{jobId}`; Comparison's Must holds; the measurement record for cut-time error
**Extends:** none
**Stubs:** Media.detectCuts, Files.get and Files.presignDownload — removed by S22 (recordCuts) and S25 (both routes); Library.setReferenceJob — removed by S25
**Requirements:** FR-2.2, FR-2.4, VR-2, VR-6
**Guards:** VR-2, FR-3.6

#### Why
The PRD's test is a style "just on a different house". This story measures each video against its own plan and puts a reproduction beside the reference video.

#### How it's checked
pytest with seeded jobs, shots and a stub cut detector.

#### Acceptance criteria
1. Cuts are measured against the plan
   Given a ready job with shots of 3.0, 2.5 and 3.5 s and detected cuts at 3.04 and 5.47 s
   When recordCuts runs
   Then cut checks show errors of +0.04 s and −0.03 s
2. Left-out shots move the expected cuts
   Given the same job with shot 2 failed
   When recordCuts runs
   Then the one expected cut is at 3.0 s
3. A missed cut is recorded, not fatal
   Given the detector finds no cut near 3.0 s
   When recordCuts runs
   Then that row has no detected time and the job stays ready
4. Re-checking replaces the rows
   Given a job with cut checks
   When recordCuts runs again
   Then the job has one row per cut, not two
5. A reference video is set
   Given the style "Golden hour" and a ready job made from its text
   When `POST /api/styles/{id}/reference` sends that job
   Then the style's reference is that job
6. Only an eligible job can be the reference
   Given a job that is still running
   When it is sent as the reference
   Then the answer is 409 `not_eligible`
7. Side by side
   Given a style with a reference job and a ready reproduction on another shoot
   When `GET /api/styles/{id}/reproductions/{jobId}` is called
   Then it returns both video links, both summaries and one row per shot position
8. Summaries count shots, movements and transitions
   Given a reference with 7 shots and a reproduction with 6
   When the comparison is read
   Then each summary shows its shot count, total length, median shot length, movements and transitions with counts
9. Flagged reproduction shots are marked
   Given the reproduction's shot 3 used the fallback model
   When the comparison is read
   Then shot 3 is marked flagged
10. No reference yet
    Given a style with no reference video
    When the comparison is requested
    Then the answer is 409 `no_reference`

#### Not in this story
- The comparison screen — picked up by S18
