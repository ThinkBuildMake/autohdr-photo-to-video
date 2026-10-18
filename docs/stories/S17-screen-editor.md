### S17 — The editor lets the photographer swap, change or remove shots and re-export

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — one screen with a timeline and per-shot edit forms
**Builds:** the Editor screen (a timeline of the shots over the song bar; per shot: swap the photo, change movement from the 12 names, speed, prompt, photo edit, length or transition, remove or put back; each card says whether it will be made again, only re-cut or is unchanged; "Re-export video")
**Extends:** none
**Stubs:** getJob, getPhotoshoot, editShot and exportJob — removed by S24
**Requirements:** FR-1.13, FR-1.14, FR-1.15, FR-1.16, DE-1
**Guards:** CH-1

#### Why
Small fixes should not mean starting over: the photographer changes the shots they want and only those are made again.

#### How it's checked
Playwright in Chromium against the app with stubbed routes.

#### Acceptance criteria
1. The timeline shows the video
   Given a ready job of 6 shots totalling 40 s
   When the editor opens
   Then 6 shot blocks sit over a 40 s song bar in order
2. Swap a photo
   Given the editor
   When shot 2's photo is swapped for another from the shoot
   Then the stubbed editShot receives the new photo and shot 2 says it will be made again
3. Movement choices are the 12 names
   Given the editor
   When shot 3's movement list is opened
   Then it lists the 12 movement names
4. A length change only re-cuts
   Given the editor
   When shot 1's length is set to 3.5 s
   Then shot 1 says it will only be re-cut
5. Remove and put back
   Given the editor
   When shot 5 is removed and then put back
   Then shot 5 shows unchanged
6. A bad edit is shown in place
   Given editShot answers 400 `invalid_edit` naming the length
   When the edit is saved
   Then the message appears next to the length field
7. Re-export
   Given one shot to remake and one to re-cut
   When "Re-export video" is clicked
   Then the stubbed exportJob is called and the Job page opens
8. Busy jobs cannot be edited
   Given a job that is running
   When the editor opens
   Then the edit controls are disabled with "This video is being made"

#### Not in this story
- Real edits and the new video version — joined in S24
