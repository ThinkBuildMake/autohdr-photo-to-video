### S19 — The repo explains how to set it up, how it is designed and how it would scale

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** S — two documents
**Builds:** the written scaling explanation; the README's setup and design sections
**Extends:** none
**Stubs:** none
**Requirements:** GC-7, SC-2, GC-8
**Guards:** none

#### Why
The submission is judged on systems engineering, and the brief asks how the product would serve more than one user at a time.

#### How it's checked
An agent follows the README's setup on a clean checkout, and checks the scaling explanation against SC-2.

#### Acceptance criteria
1. Setup works as written
   Given a clean checkout and the README
   When its setup steps are followed with `FAKE_PROVIDERS=1`
   Then the app opens and `/healthz` answers 200
2. The design is described
   Given the README
   When its design section is read
   Then it names every module and outside service in ARCHITECTURE.md
3. Scaling says what changes for N jobs
   Given the scaling explanation
   When its headings are listed
   Then it has a section on running N jobs at once that names the 30 min limit per job and says outputs stay the same
4. Scaling names its triggers
   Given the scaling explanation
   When its sections are listed
   Then there is one section per row of HIGH_LEVEL_DESIGN.md "What to add next", each quoting that row's trigger

#### Not in this story
- The README's results on the 12 test shoots — picked up by S26
