### S23 — When something fails, the photographer sees why, starts again or redoes one shot

**Kind:** wiring
**Blocked by:** S11, S22
**Review gate:** human demo
**Size:** M — three seams: the job screen's buttons to restartJob and redoShot, those to the worker, and startup recovery across Jobs and Providers
**Wires:** the restartJob, redoShot and "Startup recovery" traces, and the Pipeline failure behaviour as the user sees it. Removes the restartJob and redoShot stubs behind the Job screen
**Extends:** none
**Requirements:** FR-1.5, FR-1.6, FR-1.12, RL-1, RL-2, RL-3, QC-2
**Guards:** RL-1, RL-2, RL-3, QC-2

#### Why
Failures are shown, never hidden, and fixing one never costs the shots that already worked.

#### How it's checked
The human demo, on the deployed app:
1. Turn on the fake provider's out-of-credit answer on the third clip and submit a job; within a minute the page says the video service is out of credit, the finished shots are kept, and "Start again" shows.
2. Turn the fake off and click "Start again"; only the unfinished shots are made, and the video arrives.
3. Restart the container while a job runs; the job shows "the worker restarted" and "Start again" finishes it.
4. On a finished video from S22, click "Redo this shot" on one shot; only that shot is made again and a new version of the video appears.

#### Acceptance criteria
1. An out-of-credit stop is shown within a minute
   Given a provider answering out of credit on the third clip
   When the job reaches it
   Then within 60 s the page says the service is out of credit and shows "Start again"
2. Start again keeps finished shots
   Given the stopped job
   When "Start again" is clicked
   Then the passed shots keep their clips and only the others are made
3. A worker restart is recovered
   Given a job running when the container restarts
   When the worker comes back
   Then the job shows "the worker restarted" and "Start again"
4. A clip left at the provider is collected
   Given a clip call open when the container restarted
   When the worker comes back
   Then its clip is downloaded and its call is closed
5. One failed shot does not stop the others
   Given one shot set to fail every check
   When the job runs
   Then the other shots pass and the failed one is marked with "flagged every attempt"
6. Redo one shot
   Given a ready video
   When "Redo this shot" is clicked on shot 2
   Then only shot 2 is made again and the video's version goes up by one
7. Interrupted labelling and planning resume
   Given a shoot labelling and a job planning when the app restarted
   When the app comes back
   Then both finish without the photographer doing anything
8. The seams join the gate
   Given the regression gate
   When it runs
   Then it holds integration cases for restart, redo and startup recovery across the real Jobs and Pipeline with fakes, including out of credit, rate limit and refusal

#### Not in this story
- Editor edits — picked up by S24
