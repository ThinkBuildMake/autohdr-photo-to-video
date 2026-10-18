### S21 — Choose a style, edit its text and get a shot plan for a real photoshoot

**Kind:** wiring
**Blocked by:** S03, S09, S20
**Review gate:** human demo
**Size:** M — four seams: Styles and New video screens to Library and Jobs, Jobs to Library, Jobs to Photoshoots, Jobs to the planner on OpenRouter
**Wires:** the listStyles, getStyle, listSongs, createStyle, createJob, replanJob and updateJobShots traces, and planJob. Removes the stubs for Library.getStyle, Photoshoots.listPhotos, Providers.planShots and allowedLengths in Jobs, Files.presignDownload in Library, and the Library and Jobs routes behind the Styles and New video screens
**Extends:** none
**Requirements:** FR-1.2, FR-1.10, FR-2.5, VR-3
**Guards:** CH-1, FR-3.6

#### Why
The photographer sees what will be made before paying for it: the style text turned into shots from their own photos.

#### How it's checked
The human demo, on the deployed app, with the seeded songs and two presets, and the shoot uploaded in S20:
1. Open Styles; the presets show their text, author and song.
2. Click "Use this style" on one; edit the text to add "End on a Dolly Out."; pick the uploaded shoot.
3. The plan appears: one card per shot with photo, movement, speed, length, transition and the words of the text it follows; the last shot is a Dolly Out.
4. Change one card's movement, remove one shot, save; reload and the changes are kept.
5. Change the text to ask for a pool; re-plan; the banner says there is no pool photo.
6. Click "Save as my style"; the new style appears on Styles.

#### Acceptance criteria
1. A preset fills the form from the real library
   Given the seeded presets
   When "Use this style" is clicked
   Then the form holds that preset's text and song
2. The real planner writes the plan
   Given the uploaded shoot and the edited text
   When the job is created
   Then a plan appears with one card per shot using photos from that shoot
3. The plan follows the text
   Given text ending "End on a Dolly Out."
   When the plan appears
   Then its last shot is Dolly Out
4. Edits are kept
   Given a changed movement and a removed shot
   When the plan is saved and the page reloaded
   Then both changes are shown
5. Missing rooms are flagged
   Given text that asks for a pool and a shoot with no pool
   When the plan is rewritten
   Then the banner says there is no pool photo
6. Saving my style
   Given an edited text and a new name
   When "Save as my style" is clicked
   Then the Styles page lists the new style with that text
7. Planner errors reach the page
   Given the planner answers `bad_response` twice
   When the plan is written
   Then the page says the plan failed and offers "Try again"
8. The seams join the gate
   Given the regression gate
   When it runs
   Then it holds integration cases for createJob through planJob with the real Library and Photoshoots and the fake planner, including an invalid plan and a missing style

#### Not in this story
- Submitting the plan — picked up by S22
