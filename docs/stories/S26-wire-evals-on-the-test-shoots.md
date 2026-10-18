### S26 — Run every test shoot, review the shots, and put the results in the README

**Kind:** wiring
**Blocked by:** S14, S19, S25
**Review gate:** human demo
**Size:** M — two seams, plus about 20 real jobs counted as generation time and the reviewer's sheet
**Wires:** the "Evals" trace (importPhotoshoot, createJob and submitJob per shoot, reports). Removes the importPhotoshoot, createJob and submitJob stubs in Evals
**Extends:** the README written in S19 (adds its results section)
**Requirements:** EV-1, EV-2, GC-6, GC-8, GC-9, VR-1, VR-3, VR-4, VR-5, QC-1, PF-1, PF-2
**Guards:** GC-9, CO-1

#### Why
The PRD judges consistent professional output on its 12 test shoots. This is where the reviewer counts what the system cannot.

#### How it's checked
The human demo:
1. Before the runs: each preset gets a try on its demo shoot and a reference video through Create a style.
2. Show `evals import` loading the 12 test shoots from the downloaded folder, and the repo with no test photos in it.
3. Show the EV-1 and EV-2 runs' jobs on the Jobs page.
4. The reviewer has watched every EV-1 and EV-2 video and filled the sheet; run `evals report`.
5. Read the report: per video visibly AI shots, rooms changed, cut error and job time; per style the reproduction checks; the check's catch rate.
6. Run the metrics report; panel 2 shows the median over the EV-1 jobs.
7. Read the README's results section.

#### Acceptance criteria
1. The 12 shoots are imported
   Given the downloaded test folder
   When `evals import` runs
   Then the Jobs page can start a job on each of the 12 shoots
2. Every preset has a reference video
   Given the 2–3 demo presets
   When each is tried on its demo shoot and its chosen try marked
   Then the Styles page shows every preset with a reference video
3. EV-1 makes 12 videos
   Given a demo style
   When the EV-1 run finishes
   Then the report covers 12 videos, each with its job time
4. EV-2 makes each preset's reproductions
   Given each preset with a reference video
   When the EV-2 run finishes
   Then each preset has reproductions on 2 shoots other than its demo shoot
5. The reviewer's counts are reported
   Given the filled reviewer sheet
   When `evals report` runs
   Then each video shows its visibly AI shots and rooms changed, and each style its movement, transition and look results
6. The check's catch rate is reported
   Given the filled sheet
   When the report is read
   Then it shows how many reviewer-failed shots the check flagged
7. The README shows the results
   Given the final report
   When the README is read
   Then its results section gives the per-video and per-style numbers
8. No test photos are committed
   Given the repository after the run
   When the gate's photo check runs
   Then it passes
9. The seams join the gate
   Given the regression gate
   When it runs
   Then it holds integration cases for import and run across the real Photoshoots and Jobs with Providers on mocked OpenRouter answers, including a stopped job
10. Every video is reviewed
    Given the EV-1 and EV-2 videos
    When the sheet is read
    Then every shot of every video has its visibly-AI and room-changed marks
11. The typical wait time shows real numbers
    Given the EV-1 jobs
    When the metrics report runs
    Then panel 2 shows their median submit-to-playable time

#### Not in this story
- The demo rehearsal — picked up by S27, which does not wait for the evals
