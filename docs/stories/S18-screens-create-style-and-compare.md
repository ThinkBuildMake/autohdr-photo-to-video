### S18 — Create a style, try it on a demo shoot, and lay a reproduction beside the reference video

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — two screens
**Builds:** the Create a style screen (name, author, style text, song with its licence, frame rate, demo photoshoot; "Try it" makes a plan and a video; revise and try again; "Use as reference video"); the Reference and reproduction screen (pick a reproduction, two players, play both, both shot plans side by side with shot count, lengths, movements, transitions and flagged shots, and cut checks against each plan)
**Extends:** none
**Stubs:** listSongs, createStyle, updateStyle, createJob, submitJob, getJob, setReference, getReproduction — removed by S25
**Requirements:** FR-2.1, FR-2.2, FR-2.3, FR-2.4, FR-3.6, DE-1
**Guards:** FR-3.6, GC-5

#### Why
A style author writes a style and tries it until it looks right; then anyone can check that it holds on a different house.

#### How it's checked
Playwright in Chromium against the app with stubbed routes.

#### Acceptance criteria
1. A style is written
   Given the Create a style page
   When name "Golden hour", author "Sam", a style text, song "Track A", 24 fps and demo shoot "Test shoot A" are entered and "Try it" is clicked
   Then the stubbed createStyle and createJob receive those values
2. Only text describes the style
   Given the Create a style page
   When the page is inspected
   Then it has no video upload control
3. The song's licence is shown
   Given song "Track A" is chosen
   When the song picker closes
   Then its licence and credit show beside it
4. The try is shown
   Given a stubbed ready job for the try
   When it finishes
   Then its plan and its video show on the page
5. Revise and try again
   Given a finished try
   When the text is changed and "Try it" is clicked again
   Then updateStyle and a new createJob are called
6. Use as reference video
   Given a finished try
   When "Use as reference video" is clicked
   Then the stubbed setReference receives that job
7. Two players side by side
   Given a stubbed comparison
   When the Reference and reproduction page opens
   Then two players show, with a "Play both" button
8. Both plans side by side
   Given a reference of 7 shots and a reproduction of 6
   When the page opens
   Then the summary shows both counts, lengths, movements and transitions, and the shot rows line up by position
9. Flagged shots and cut checks show
   Given reproduction shot 3 flagged and a worst cut error of 0.06 s
   When the page opens
   Then shot 3 is marked and 0.06 s is shown
10. No reference yet
    Given getReproduction answers 409 `no_reference`
    When the page opens
    Then it says the style has no reference video yet

#### Not in this story
- Real tries and comparisons — joined in S25
