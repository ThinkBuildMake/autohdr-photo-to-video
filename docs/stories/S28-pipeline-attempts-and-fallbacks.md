### S28 — The worker tries each shot up to four times and switches model when one keeps failing

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — per-shot steps 4 and 5: clip, check, attempts and the video model fallback
**Builds:** per-shot steps 4 and 5 (generate, check with frames, up to 4 attempts per round, the fallback video model after a refusal or two failures); Pipeline's Must holds "a clip is used only if its check passed" and "provider errors reported within 60 s"; Pipeline's Failure behaviour rows "Rate limited or timeout", "Provider refuses", "All 4 attempts flagged"; the measurement records for RL-1 and for shots dropped because every attempt was flagged
**Extends:** none
**Stubs:** Jobs worker interface, Providers (generateClip, checkClip), Media (extractFrames), Files (put) — removed by S22
**Requirements:** QC-2, RL-1, OB-2
**Supports:** FR-1.7 (shown in S22)
**Guards:** QC-2, RL-1, FR-1.7

#### Why
A clip that looks AI-made is never delivered: it is made again, up to the limit, and a model that keeps failing is swapped for the fallback.

#### How it's checked
pytest running the worker once against stubbed Jobs, Providers, Media and Files with scripted checks and errors.

#### Acceptance criteria
1. A flagged clip is tried again
   Given shot 2's first check is flagged and its second passes
   When the worker runs the job
   Then shot 2 is passed with 2 attempts and its clip is attempt 2's
2. Four flags fail the shot
   Given shot 3 is flagged on every check
   When the worker runs the job
   Then shot 3 has 4 attempts and is failed with `flagged_every_attempt`
3. A refusal moves to the fallback model
   Given Veo 3.1 refuses shot 4
   When the next attempt starts
   Then it uses Seedance 2.0 and the shot shows the fallback
4. Two failures move to the fallback model
   Given Veo 3.1 answers `failed` twice on shot 5
   When the third attempt starts
   Then it uses Seedance 2.0
5. A rate limit counts as an attempt
   Given a clip request answers `rate_limited`
   When the worker records it
   Then the shot shows "Provider busy, trying again" and the attempt counts toward the 4
6. An error is shown within a minute
   Given a clip request fails with `failed`
   When the worker records it
   Then the attempt's error is written within 60 s of the provider's answer

#### Not in this story
- The deadline, stops and assembly — picked up by S30
