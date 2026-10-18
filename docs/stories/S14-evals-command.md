### S14 — One command runs the 12 test shoots and writes the reports a reviewer fills in

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — three commands, a reviewer sheet and a report
**Builds:** the Evals module: `evals import`, `evals run --suite ev1 | ev2`, `evals report`; the reviewer sheet; the report files; the Evals data flow on the command side
**Extends:** none
**Stubs:** Photoshoots.importPhotoshoot and Jobs.createJob and submitJob — removed by S26
**Requirements:** EV-1, EV-2, GC-6, GC-9
**Guards:** GC-9

#### Why
VR-1 and VR-3 to VR-6 need a person to judge each shot. This story runs the jobs, lays out what to judge, and turns the filled sheet into numbers.

#### How it's checked
pytest running each command against stubbed imports and seeded finished jobs, on synthetic shoots.

#### Acceptance criteria
1. Shoots are imported once
   Given a folder with 12 subfolders of synthetic photos
   When `evals import` runs twice
   Then 12 photoshoots exist, not 24
2. EV-1 runs a style on every shoot
   Given 12 imported shoots and the style "Golden hour"
   When `evals run --suite ev1 --style "Golden hour"` runs
   Then 12 jobs are created and submitted
3. EV-2 skips the demo shoot
   Given a style whose demo shoot is shoot 1
   When `evals run --suite ev2` runs for it
   Then reproductions are made on 2 other shoots and not shoot 1
4. The sheet lists every attempt
   Given finished jobs with 30 attempts, 4 of them flagged
   When the run writes the reviewer sheet
   Then it has 30 rows with clip links and empty columns for visibly AI, room changed, movement matches and transition matches
5. The sheet asks about each plan and each reproduction
   Given EV-2 reproductions of one style on 2 shoots
   When the run writes the reviewer sheet
   Then it has one row per plan for "text followed" and one row per reproduction for "looks like the reference"
6. The report adds up the sheet
   Given a filled sheet marking 2 shots visibly AI in video 1
   When `evals report` runs
   Then video 1's row shows 2 visibly AI shots, its rooms changed, its worst cut error and its job time
7. The check's catch rate is reported
   Given the reviewer failed 5 attempts and the check flagged 3 of them
   When `evals report` runs
   Then the report shows 3 of 5 caught
8. A stopped job is reported, and the run goes on
   Given one of 12 jobs stops with `out_of_credit`
   When the report is written
   Then that job is listed with its reason and the other 11 are reported
9. No photos in the reports
   Given a written report
   When the report folder is listed
   Then it holds only text and number files
10. The report gives the style checks
    Given a filled sheet with one reproduction judged not like its reference
    When `evals report` runs
    Then that style's row shows 1 of 2 reproductions matching and its plans' text-followed count
11. The report gives the median job time
    Given EV-1 jobs of 8, 10 and 14 minutes
    When `evals report` runs
    Then it shows a median job time of 10 minutes

#### Not in this story
- Running against the 12 real test shoots — picked up by S26
