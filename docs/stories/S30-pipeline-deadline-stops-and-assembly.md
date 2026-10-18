### S30 — The worker keeps a job inside 30 minutes, stops it cleanly, and cuts the passed shots to the song

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — the run deadline, the stop cases, assembly and the worker side of startup recovery
**Builds:** the run deadline (no clip after `deadline_at`); the stop cases (out of credit, no shot passed, assembly failed); assembly of the passed shots not removed; recordCuts after finishing; the worker side of startup recovery (calling recoverInterrupted and recoverCalls first); Pipeline's Must holds "one shot failing never stops the others" and "no clip after the deadline"; Pipeline's Failure behaviour rows "Out of credit", "Deadline reached", "Assembly fails"
**Extends:** none
**Stubs:** Jobs worker interface, Providers (generateClip), Media (assemble), Files (put) and Comparison.recordCuts — removed by S22
**Requirements:** PF-1, PF-3, RL-3, CH-2
**Supports:** FR-1.4, FR-1.6 (shown in S22 and S23)
**Guards:** PF-1, PF-3, RL-3

#### Why
The video is due within 30 minutes; one bad shot must not take the others down; and when the service runs out of credit, nothing finished is lost.

#### How it's checked
pytest running the worker once against stubbed Jobs, Providers, Media, Files and Comparison, with a fake clock.

#### Acceptance criteria
1. One failed shot leaves the rest
   Given shot 3 fails and the other 5 pass
   When the worker finishes
   Then the video holds 5 shots and the job is `ready_with_failures`
2. No clip after the deadline
   Given a fake clock 29 minutes into the run and shot 5 flagged
   When the worker decides its next attempt
   Then no clip is requested and shot 5 fails with `out_of_time`
3. Out of credit stops the job
   Given a clip request answers `out_of_credit`
   When the worker sees it
   Then the job is stopped with `out_of_credit` and passed shots are kept
4. No shot passed
   Given every shot fails
   When the worker finishes
   Then the job is stopped with `no_shot_passed` and every reason is listed
5. Assembly failure stops the job
   Given assemble raises MediaError
   When the worker assembles
   Then the job is stopped with `assembly_failed` and the clips are kept
6. Removed shots are left out
   Given a job with shot 5 removed
   When the worker assembles
   Then assemble receives every passed shot but shot 5, in position order
7. Cuts are recorded after finishing
   Given a job that finished ready
   When the worker is done
   Then recordCuts was called once for it
8. Restart recovery runs first
   Given the worker starts
   When its loop begins
   Then recoverInterrupted and recoverCalls have run before any job is claimed
9. Two separate runs give the same video
   Given the same job and fake providers run on two separate databases and buckets
   When both finish
   Then the two videos have the same shots, lengths and cuts as a single run
10. A re-cut-only export re-assembles
    Given a queued job with no pending shots and shot 1's length changed
    When the worker runs it
    Then no clip is requested and a new video is cut from the final clips

#### Not in this story
- Real provider, media and bucket calls — joined in S22
