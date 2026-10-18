### S26 — Run every test shoot, review the shots, and put the results in the README

**Kind:** wiring
**Blocked by:** S14, S19, S25
**Review gate:** human demo
**Size:** L — 12 or more real jobs across the Evals to Photoshoots and Evals to Jobs seams, then the reviewer's sheet
**Wires:** the "Evals" trace (importPhotoshoot, createJob and submitJob per shoot, reports). Removes the importPhotoshoot, createJob and submitJob stubs in Evals
**Extends:** the README written in S19 (adds its results section)
**Requirements:** EV-1, EV-2, GC-6, GC-8, GC-9, VR-1, VR-3, VR-4, VR-5, QC-1, PF-1, PF-2
**Guards:** GC-9, CO-1

#### Why
The PRD judges consistent professional output on its 12 test shoots. This is where the reviewer counts what the system cannot.

#### How it's checked
The human demo:
1. Show `evals import` loading the 12 test shoots from the downloaded folder, and the repo with no test photos in it.
2. Show the EV-1 and EV-2 runs' jobs on the Jobs page.
3. Fill the reviewer sheet for a few videos together; run `evals report`.
4. Read the report: per video visibly AI shots, rooms changed, cut error and job time; per style the reproduction checks; the check's catch rate.
5. Read the README's results section.

#### Acceptance criteria
1. The 12 shoots are imported
   Given the downloaded test folder
   When `evals import` runs
   Then the Jobs page can start a job on each of the 12 shoots
2. EV-1 makes 12 videos
   Given a demo style
   When the EV-1 run finishes
   Then the report covers 12 videos, each with its job time
3. EV-2 makes each preset's reproductions
   Given each preset with a reference video
   When the EV-2 run finishes
   Then each preset has reproductions on 2 shoots other than its demo shoot
4. The reviewer's counts are reported
   Given the filled reviewer sheet
   When `evals report` runs
   Then each video shows its visibly AI shots and rooms changed, and each style its movement, transition and look results
5. The check's catch rate is reported
   Given the filled sheet
   When the report is read
   Then it shows how many reviewer-failed shots the check flagged
6. The README shows the results
   Given the final report
   When the README is read
   Then its results section gives the per-video and per-style numbers
7. No test photos are committed
   Given the repository after the run
   When the gate's photo check runs
   Then it passes
8. The seams join the gate
   Given the regression gate
   When it runs
   Then it holds integration cases for import and run across the real Photoshoots and Jobs with fakes, including a stopped job

#### Not in this story
- The demo rehearsal — picked up by S27
