### S22 — Make a real video: the worker generates every shot and the photographer plays and downloads it

**Kind:** wiring
**Blocked by:** S05, S07, S10, S12, S13, S16, S21, S28, S29, S30
**Review gate:** human demo
**Size:** L — first real end-to-end job across five seams: Jobs to the worker, the worker to Providers on OpenRouter, to Media, to Files and the bucket, and to Comparison.recordCuts; plus the job screens to Jobs
**Wires:** the submitJob, listJobs, getJob, getVideo and "Run next job" traces, and Comparison.recordCuts. Removes the stubs for the Jobs worker interface, Providers, Media, Files and recordCuts in Pipeline (S12, S28, S30); Files.presignDownload in Jobs; Media.detectCuts and Files.get in recordCuts; and the Jobs routes behind the Jobs and Job screens
**Extends:** none
**Requirements:** FR-1.3, FR-1.4, FR-1.7, FR-1.8, FR-1.9, FR-1.11, SC-1, PF-1, PF-3, DE-5, GC-5, OB-1, OB-2, CO-1, VR-2, VR-6
**Guards:** PF-1, PF-3, QC-2, VR-5, FR-1.7, DE-5

#### Why
This is the product: a real video from real photos in a chosen style, inside 30 minutes.

#### How it's checked
The human demo, on the deployed app with real providers, using the plan from S21:
1. Click "Make my video"; the Job page shows each shot moving through editing, generating and checking.
2. Start a second job on another shoot; its page says it is waiting for the first.
3. Close the tab, then open Jobs and reopen the first job.
4. When it is ready, play it, download it, and read the song credit; any failed shot is marked beside the player with its reason; crop-only and fallback shots say so.
5. Run the metrics report; wait time, attempts per shot, shots dropped and cut error now show this job's numbers.

#### Acceptance criteria
1. A real job finishes in time
   Given a submitted job on a test shoot
   When the worker runs it with the real providers
   Then the Job page shows a playable video within 30 minutes of submitting
2. Progress shows while it runs
   Given the job running
   When the Job page is open
   Then each shot's status and attempt change as the worker records them
3. The second job waits, then runs
   Given the first job running
   When a second job is submitted
   Then its page says it is waiting, and it starts after the first finishes
4. The photographer can come back
   Given the tab closed during the run
   When the Jobs page is opened and the job clicked
   Then its current status or video is shown
5. The video is the right format
   Given the finished video
   When it is downloaded and probed
   Then it is 1920 × 1080 at the style's frame rate
6. The video follows its plan
   Given the finished video
   When its cut checks are read
   Then every detected cut is within 0.1 s of the plan
7. The song is credited
   Given the finished video
   When the Job page is read
   Then the credit shows the song's title, artist, licence and source
8. Only passed clips are delivered
   Given a shot whose first attempt was flagged
   When the Job page is read
   Then its clip is the passed attempt's
9. The job's record is complete
   Given the finished job
   When its job, shots and attempts are read
   Then each shot has its photo, edit prompts, prompt, model, attempts and result, every flagged attempt has its score, and the job has its time and total cost
10. The metrics show real numbers
    Given the finished job
    When the metrics report runs
    Then wait time, attempts per shot, shots dropped and cut error show this job's values
11. The seams join the gate
    Given the regression gate
    When it runs
    Then it holds integration cases for a full job across the real Jobs, Pipeline, Providers on mocked OpenRouter answers, Media, Files on moto and Comparison, including a flagged attempt and a failed shot
12. Photos are edited toward the style
    Given a shot with photo-edit prompts
    When the job finishes
    Then the Job page shows the shot edited, or crop only with the reason
13. The video plays and downloads
    Given the finished job
    When the photographer presses play and then the download link
    Then the video plays in the page and the downloaded file has the same length

#### Not in this story
- Stops, Start again and Redo — picked up by S23
