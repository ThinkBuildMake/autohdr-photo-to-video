### S12 — The worker makes every shot of a queued job and cuts the video to the song

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** L — the first async job: parallel shots, attempts, fallbacks, the run deadline, assembly and failure handling
**Builds:** Pipeline runNextJob (the worker loop); the per-shot steps (crop, photo-edit chain with check and crop-only fallback, prompt with the lock text, clip, check, up to 4 attempts, fallback models); assembly of the passed shots not removed; the Make the video data flow on the worker side; the worker side of startup recovery (calling recoverInterrupted and recoverCalls); Pipeline's Must holds and Failure behaviour
**Extends:** none
**Stubs:** Jobs worker interface, Providers (editPhoto, checkEdit, generateClip, checkClip), Media (crop16x9, extractFrames, assemble), Files (get, put) and Comparison.recordCuts — removed by S22
**Requirements:** FR-1.4, FR-1.5, FR-1.6, FR-1.7, FR-1.8, PF-1, PF-3, RL-1, RL-3, QC-2, VR-5, OB-1, CH-2
**Guards:** PF-1, PF-3, RL-1, RL-3, QC-2, VR-5, FR-1.7

#### Why
This is where the video gets made. Shots run at once to fit 30 minutes, a flagged clip is tried again, and one bad shot never stops the rest.

#### How it's checked
pytest running the worker once against stubbed Jobs, Providers, Media, Files and Comparison, with scripted check results, errors and a fake clock.

#### Acceptance criteria
1. Every shot runs at once
   Given a claimed job with 6 pending shots and 6 shots allowed in flight
   When the worker runs it
   Then all 6 clip requests start before any finishes
2. A flagged clip is tried again
   Given shot 2's first check is flagged and its second passes
   When the worker runs the job
   Then shot 2 is passed with 2 attempts and its clip is attempt 2's
3. Four flags fail the shot
   Given shot 3 is flagged on every check
   When the worker runs the job
   Then shot 3 has 4 attempts and is failed with `flagged_every_attempt`
4. One failed shot leaves the rest
   Given shot 3 fails and the other 5 pass
   When the worker finishes
   Then the video holds 5 shots and the job is `ready_with_failures`
5. A risky edit falls back to the crop
   Given every photo-edit check reports a changed window
   When shot 1 is prepared
   Then shot 1 uses the crop with `crop_only` and a note
6. The full prompt is stored
   Given shot 1 with movement Dolly In and speed slow
   When its attempt starts
   Then the attempt's prompt holds the movement prompt, the speed and the lock text
7. A refusal moves to the fallback model
   Given Veo 3.1 refuses shot 4
   When the next attempt starts
   Then it uses Seedance 2.0 and the shot shows the fallback
8. Clip length covers the shot
   Given a shot of 4.5 s with a 0.5 s crossfade on a model allowing 4, 6 and 8 s
   When its clip is requested
   Then the request asks for 6 s
9. No clip after the deadline
   Given a fake clock 29 minutes into the run and shot 5 flagged
   When the worker decides its next attempt
   Then no clip is requested and shot 5 fails with `out_of_time`
10. Out of credit stops the job
    Given a clip request answers `out_of_credit`
    When the worker sees it
    Then the job is stopped with `out_of_credit` and passed shots are kept
11. An error is shown within a minute
    Given a clip request fails with `failed`
    When the worker records it
    Then the attempt's error is written within 60 s of the provider's answer
12. No shot passed
    Given every shot fails
    When the worker finishes
    Then the job is stopped with `no_shot_passed` and every reason is listed
13. Assembly failure stops the job
    Given assemble raises MediaError
    When the worker assembles
    Then the job is stopped with `assembly_failed` and the clips are kept
14. Cuts are recorded after finishing
    Given a job that finished ready
    When the worker is done
    Then recordCuts was called once for it
15. Restart recovery runs first
    Given the worker starts
    When its loop begins
    Then recoverInterrupted and recoverCalls have run before any job is claimed
16. Two separate runs give the same video
    Given the same job and fake providers run on two separate databases and buckets
    When both finish
    Then the two videos have the same shots, lengths and cuts as a single run
17. A rate limit counts as an attempt
    Given a clip request answers `rate_limited`
    When the worker records it
    Then the shot shows "Provider busy, trying again" and the attempt counts toward the 4
18. Temporary files stay off the volume
    Given a job run to the end
    When the worker finishes
    Then no temporary file is left on the database volume

#### Not in this story
- Real provider, media and bucket calls — joined in S22
