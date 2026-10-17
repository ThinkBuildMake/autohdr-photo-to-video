# KEY_METRICS.md — AutoHDR Photo-to-Video

## What success means

The user is a novice photographer who must hand an agent a video that looks like a top videographer's, without the skills to shoot or edit one (`USERS.md` §1). The problem is AutoHDR's account only, with no measured baseline (`USERS.md` §9).

Success means the photographer gets a video in the chosen style that they would send to the agent, without seeing a shot that looks AI-generated.

## No success metric (by decision)

This document has no success metric. Whether a video would pass as a professional's work is a human judgment, and the system can't count it. Counting downloads or finished jobs would measure that the feature is used, not that the need is met. That judgment is made by the reviewer in the evals (`REQUIREMENTS.md` EV-1, EV-2), not tracked here. A single metric gets added only if one appears that the system can count and that stays high only when the need is met.

## Guarantee metrics

Each threshold is copied from `REQUIREMENTS.md`. All of them can drift without a code change, because the video and image providers' speed, failure rate and free-tier limits change on their side.

| Metric | Requirement | Threshold | Measured on | Recorded from |
|---|---|---|---|---|
| **Video wait time (slowest)** | PF-1 | ≤ 30 min from submit to playable, including regeneration | Max over the 12 test jobs and every demo run | Job log: submit and ready timestamps (OB-1) |
| **Video wait time (typical)** | PF-2 | Median ≤ 10 min | Median over the same jobs | Same timestamp pair |
| **Time to tell the user about a provider error** | RL-1 | ≤ 60 s from the error | Worst case over injected failures and real errors | Job log: error and user-message timestamps |
| **Regeneration attempts per shot** | QC-2 | ≤ 3 before the shot is reported failed | Max over all shots in a job | Job log: attempts per shot (OB-1) |
| **Delivered shots the automatic check still flags** | VR-1 (proxy) | ≤ 2 per video, target 0 | Per delivered video, worst of the 12 test videos | Job log: check score of each final shot (OB-2) |
| **Spend on paid services** | CO-1, GC-3 | $0 | Whole project, checked after every test run | Provider usage and billing pages |

The check-flagged count counts only what the automatic check catches. A shot it misses still counts as fine here, so VR-1 itself stays a reviewer check.

## Upstream fixes and open questions

- QC-1 has no final threshold until the first 12 test videos run, and the flagged-shots metric inherits that weakness → set QC-1 after the first run.
- A "download or discard" action on a finished video would give the system a record of whether the photographer kept it → add it as a functional requirement if a success metric is wanted later.
- Free-tier usage versus limit has no requirement threshold (CO-1 says only "stops and says so") → add a row to `REQUIREMENTS.md` once the models are chosen and their limits are known; the metric stays out until then.
