### S12 — The worker prepares each shot's first frame and builds its prompt

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — the photo steps of each shot: crop, the photo-edit chain, its check and fallbacks, the prompt
**Builds:** Pipeline runNextJob (the worker loop: polling, parallel shots up to the setting); per-shot steps 1 to 3 (crop, photo-edit chain with check, one retry, the image model fallback, crop-only fallback; the prompt with the lock text; the clip length that covers the shot); Pipeline's Must hold "temporary files never on the volume"
**Extends:** none
**Stubs:** Jobs worker interface, Providers (editPhoto, checkEdit), Media (crop16x9), Files (get, put) — removed by S22
**Requirements:** VR-5, OB-1
**Supports:** FR-1.8 (shown in S22)
**Guards:** VR-5, PF-1

#### Why
Each shot starts from the photographer's photo, improved as the plan says, without ever changing a room. If the edit cannot be trusted, the crop is used and the shot says so.

#### How it's checked
pytest running the worker once against stubbed Jobs, Providers, Media and Files with scripted edit checks.

#### Acceptance criteria
1. Every shot runs at once
   Given a claimed job with 6 pending shots and 6 shots allowed in flight
   When the worker runs it
   Then all 6 shots start before any finishes
2. Edits run in order
   Given shot 1 with two photo-edit prompts
   When it is prepared
   Then editPhoto is called with the first prompt and then the second, on the crop
3. A changed room retries the chain once
   Given the first edit check reports a changed window and the second reports none
   When shot 1 is prepared
   Then shot 1 uses the edited photo
4. Two changed rooms fall back to the crop
   Given every edit check reports a changed window
   When shot 1 is prepared
   Then shot 1 uses the crop with `crop_only` and a note
5. A failing image model moves to its fallback
   Given the image model refuses shot 2's edit
   When shot 2 is prepared
   Then the chain is run again on the fallback image model
6. The full prompt is stored
   Given shot 1 with movement Dolly In and speed slow
   When its attempt starts
   Then the attempt's prompt holds the movement prompt, the speed and the lock text
7. Clip length covers the shot
   Given a shot of 4.5 s with a 0.5 s crossfade on a model allowing 4, 6 and 8 s
   When its clip is requested
   Then the request asks for 6 s
8. Temporary files stay off the volume
   Given a job run to the end
   When the worker finishes
   Then no temporary file is left on the database volume

#### Not in this story
- Attempts, checks and model fallbacks — picked up by S28
- The deadline, stops and assembly — picked up by S30
