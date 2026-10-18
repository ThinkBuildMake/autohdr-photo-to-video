### S16 — The Jobs list and the Job page show progress, failures and the finished video

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — two screens with five job states and the shot table
**Builds:** the Jobs screen (every job with its status, opening a job); the Job screen in each state (running with which shot and its attempt, waiting behind another job, stopped with the shot and reason and "Start again", ready with failed shots marked, ready), the shot table with status, reason, crop-only and fallback notes and "Redo this shot", the player, the download link and the song credit
**Extends:** none
**Stubs:** listJobs, getJob, getVideo, restartJob and redoShot — removed by S22 and S23
**Requirements:** FR-1.3, FR-1.5, FR-1.6, FR-1.9, FR-1.11, FR-1.12, SC-1, GC-5, RL-2, DE-1
**Guards:** RL-1, RL-2, GC-5

#### Why
The photographer leaves while the video is made and comes back to it. Nothing that failed is hidden.

#### How it's checked
Playwright in Chromium against the app with stubbed routes returning each job state.

#### Acceptance criteria
1. Jobs are listed
   Given stubbed jobs, one running and one ready
   When the Jobs page opens
   Then both are listed with style, shoot, status and elapsed time, newest first
2. A job reopens
   Given the Jobs page
   When the ready job is clicked
   Then its Job page opens
3. Running shows each shot
   Given a running job where shot 2 is "Attempt 2 of 4: flagged, a person appears"
   When the Job page opens
   Then the shot table shows that text for shot 2
4. The page updates itself
   Given a running job whose shot 1 becomes passed
   When 5 seconds pass
   Then shot 1 shows passed without a reload
5. Waiting is shown
   Given a queued job waiting behind job A
   When the Job page opens
   Then it says "Waiting for job A to finish"
6. Stopped names the shot and the reason
   Given a stopped job with reason `out_of_credit`
   When the Job page opens
   Then it says the video service is out of credit and shows "Start again"
7. Failed shots are marked on a finished video
   Given a ready-with-failures job where shot 3 failed with `flagged_every_attempt`
   When the Job page opens
   Then shot 3 is marked failed with the check's notes beside the player
8. Departures are shown on the shot
   Given shot 1 used the crop only and shot 4 the fallback model
   When the Job page opens
   Then shot 1 shows "crop only" with its note and shot 4 shows the fallback model
9. The video plays and downloads
   Given a ready job
   When the Job page opens
   Then the player plays the video and the download link saves the file
10. The song is credited
    Given a ready job with song "Track A" by "Artist A", BY-NC
    When the Job page opens
    Then the credit shows title, artist, licence and source link
11. Start again and Redo call their routes
    Given a stopped job and a ready job
    When "Start again" and "Redo this shot" on shot 2 are clicked
    Then the stubbed restartJob and redoShot for shot 2 are called
12. Times show in local time
    Given a job submitted at 17:00 UTC
    When the Job page opens in a browser set to UTC−7
    Then it shows the submit time as 10:00

#### Not in this story
- Real job data — joined in S22 and S23
