### S15 — The Styles page and the New video page: pick a style, upload photos, check the shot plan

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — two screens with uploads, polling and an editable plan
**Builds:** the Styles screen (preset cards with text, author and song; "Use this style"; "See reproductions"; "Create a style"); the New video screen (style text field filled from a preset and editable, song picker with credit, "Save as my style", drop zone and photo grid with refused files and their reasons, the shot plan as one editable card per shot with its plan note, the planner's notes for missing rooms, "Make my video")
**Extends:** none
**Stubs:** the Library, Photoshoots and Jobs routes (listStyles, getStyle, listSongs, createStyle, createUpload, completeUpload, getPhotoshoot, createJob, replanJob, updateJobShots, getJob, submitJob) — removed by S20, S21 and S22 (submitJob)
**Requirements:** DE-1
**Supports:** FR-1.1, FR-1.2, FR-1.10, FR-2.5 (shown in S20 and S21)
**Guards:** DE-1, DE-2

#### Why
This is where the photographer starts: a style as text, the photos, and a plan they can read and change before anything is made.

#### How it's checked
Playwright in Chromium against the app with stubbed routes.

#### Acceptance criteria
1. Presets show their text and song
   Given stubbed presets "Golden hour" and "Crisp modern"
   When the Styles page opens
   Then both cards show their name, author, text and song
2. A preset fills the form
   Given the Styles page
   When "Use this style" is clicked on "Golden hour"
   Then the New video page opens with its text and song filled in
3. The text can be edited
   Given the filled form
   When the photographer types "End on a Dolly Out." at the end
   Then the field holds the edited text
4. Save as my style
   Given an edited text and the name "My golden hour"
   When "Save as my style" is clicked
   Then the stubbed createStyle receives that name, text and song
5. Dropped photos are uploaded
   Given 3 JPEGs dropped on the drop zone
   When the uploads finish
   Then the grid shows 3 thumbnails
6. Refused files say why
   Given a 30 MB JPEG and an `.mp4` dropped with valid photos
   When the stub refuses them
   Then the grid lists both with "too large" and "wrong type"
7. The plan appears when it is ready
   Given a job whose plan is `planning` and then `ready` with 6 shots
   When the page polls
   Then 6 shot cards appear, each with photo, movement, speed, length, transition and plan note
8. A shot card is changed
   Given the plan cards
   When shot 3's movement is set to Crane Up and saved
   Then the stubbed updateJobShots receives shot 3 with `crane_up`
9. A shot is removed
   Given 6 plan cards
   When shot 4 is removed and the plan saved
   Then the saved plan has 5 shots
10. A shot is added
    Given 6 plan cards
    When a shot is added with movement Dolly Out and the plan saved
    Then the saved plan has 7 shots ending with Dolly Out
11. Missing rooms are shown
    Given a plan note "the text asks for a pool; no pool photo"
    When the plan appears
    Then a banner shows that note above the cards
12. Make my video
    Given a ready plan
    When "Make my video" is clicked
    Then the stubbed submitJob is called and the Job page opens

#### Not in this story
- Real uploads and real plans — joined in S20 and S21
