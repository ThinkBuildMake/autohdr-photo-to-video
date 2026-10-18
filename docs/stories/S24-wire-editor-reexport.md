### S24 — Edit a finished video and re-export it, remaking only the shots that changed

**Kind:** wiring
**Blocked by:** S11, S17, S22
**Review gate:** human demo
**Size:** M — three seams: the editor to editShot and exportJob, exportJob to the worker, the worker's re-cut to the new video version
**Wires:** the editShot and exportJob traces through "Run next job". Removes the getJob, getPhotoshoot, editShot and exportJob stubs behind the Editor screen
**Extends:** none
**Requirements:** FR-1.13, FR-1.14, FR-1.15, FR-1.16, PF-4, CH-1
**Guards:** CH-1, PF-4

#### Why
Small fixes stay small: swap a room, change a move or drop a shot, and pay only for what changed.

#### How it's checked
The human demo, on the deployed app with real providers, on the video from S22:
1. Open the editor; swap shot 2's photo, change shot 3's movement to Crane Up, shorten shot 1, remove shot 5.
2. Each card says remade, re-cut only or unchanged.
3. Click "Re-export video"; only shots 2 and 3 are made; the new version plays within 10 minutes.
4. The untouched shots look the same as before; shot 5 is gone; the cuts follow the new lengths.

#### Acceptance criteria
1. Edits are saved
   Given the editor on a ready video
   When shot 2's photo is swapped and shot 3's movement set to Crane Up
   Then both cards say they will be made again
2. Only changed shots are made
   Given those edits plus a shorter shot 1 and shot 5 removed
   When "Re-export video" is clicked
   Then the worker makes clips for shots 2 and 3 only
3. Re-export is quick
   Given a re-export with 2 shots to remake
   When it runs
   Then the new version plays within 10 minutes of clicking
4. Untouched shots are unchanged
   Given the new version
   When its shots are compared with the old version's
   Then shots 4 and 6 use the same clips
5. Removed shots are gone and cuts move
   Given the new version
   When its cut checks are read
   Then shot 5 is absent and each cut is within 0.1 s of the new lengths
6. The old version is kept
   Given the new version
   When the bucket is read
   Then the previous video version is still there
7. The seams join the gate
   Given the regression gate
   When it runs
   Then it holds integration cases for edit and export across the real Jobs, Pipeline and Providers on mocked OpenRouter answers, including an invalid edit and a busy job
8. Speed and transition edits are used
   Given shot 6 set to speed fast and a crossfade
   When the video is re-exported
   Then shot 6 is remade fast and enters on a crossfade
9. A removed shot can be put back
   Given shot 5 removed in the editor
   When it is put back before re-exporting
   Then the new version still holds shot 5 with its old clip

#### Not in this story
- Comparing with a style's reference video — picked up by S25
