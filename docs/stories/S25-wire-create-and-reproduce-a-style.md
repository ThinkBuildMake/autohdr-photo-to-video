### S25 — Create a style on a demo shoot, mark its reference video, and compare a reproduction on another house

**Kind:** wiring
**Blocked by:** S18, S22
**Review gate:** human demo
**Size:** M — four seams, plus three real jobs counted as generation time: Create a style to Library and Jobs, Library to Photoshoots, setReference to Library, getReproduction to Jobs, Files and cut checks
**Wires:** the createStyle, updateStyle, setReference, getReproduction and "Reproduce a style and compare" traces. Removes the stubs behind the Create a style and Reference and reproduction screens, Photoshoots in Library, and Library.setReferenceJob, Files and Media in Comparison's routes
**Extends:** none
**Requirements:** FR-2.1, FR-2.2, FR-2.3, FR-2.4, FR-3.6, VR-2, VR-4, VR-6, GC-5
**Guards:** FR-3.6, GC-5, VR-2

#### Why
The PRD's style test: the same style, "just on a different house", side by side.

#### How it's checked
The human demo, on the deployed app with real providers:
1. Open Create a style; write a name, author and style text, pick a seeded song and 30 fps, choose a test shoot as the demo shoot; click "Try it".
2. Read the plan and watch the video; change one sentence of the text and try again.
3. Click "Use as reference video" on the try you prefer.
4. Run the style on a second test shoot as a reproduction.
5. Open Reference and reproduction; play both; read the summary, the shot rows and the cut checks; flagged shots are marked.

#### Acceptance criteria
1. A style is tried on its demo shoot
   Given a new style text and a test shoot
   When "Try it" is clicked
   Then a plan and then a video appear on the page
2. Revising makes a new try
   Given a changed sentence
   When "Try it" is clicked again
   Then a second video appears and the style holds the new text
3. The reference video is set
   Given two tries
   When "Use as reference video" is clicked on the second
   Then the Styles card shows the style has a reference video
4. A reproduction uses the style unchanged
   Given the style and a second test shoot
   When a reproduction is run
   Then the comparison says it used the style's text and song unchanged
5. Side by side
   Given the finished reproduction
   When Reference and reproduction opens
   Then both videos play and "Play both" starts them together
6. The comparison lists both videos' shots
   Given the comparison page
   When it is read
   Then it shows both shot counts, lengths, movements and transitions, and each video's worst cut error against its own plan
7. No outside video anywhere
   Given the style and both jobs
   When the bucket and the style are read
   Then they hold only product-made clips and videos, photos and text
8. The seams join the gate
   Given the regression gate
   When it runs
   Then it holds integration cases for createStyle, setReference and getReproduction across the real Library, Jobs and Comparison, including a not-ready reference and a style with no reference

#### Not in this story
- Reproductions on every preset and the VR-4 judgment — picked up by S26
