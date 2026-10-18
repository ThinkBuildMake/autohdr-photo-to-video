# KEY_METRICS.md — AutoHDR Photo-to-Video

## What success means

The user is a novice photographer who must hand an agent a video that looks like a top videographer's, without the skills to shoot or edit one (`USERS.md` §1). The problem is AutoHDR's account only, with no measured baseline (`USERS.md` §9).

Success means the photographer gets a video in the chosen style that they would send to the agent, without seeing a shot that looks AI-generated. This is the PRD's own bar: a video "that does not look AI generated and perfectly adheres to a video style", judged on "consistent professional level output" (PRD p.2).

## No success metric (by decision)

This document has no success metric. Whether a video would pass as a professional's work is a human judgment, and the system can't count it. Counting downloads or finished jobs would measure that the feature is used, not that the need is met. That judgment is made by the reviewer in the evals (`REQUIREMENTS.md` EV-1, EV-2), not tracked here. A single metric gets added only if one appears that the system can count and that stays high only when the need is met.

## Guarantee metrics

Each threshold is copied from `REQUIREMENTS.md`. All of them can drift without a code change, because the video and image providers' speed, failure rate, rate limits and model versions change on their side.

| Metric | Requirement | Threshold | Measured on | Recorded from |
|---|---|---|---|---|
| **Video wait time (slowest)** | PF-1 | ≤ 30 min from submit to playable, including regeneration | Max over the 12 test jobs and every demo run | Job log: submit and ready timestamps (OB-1) |
| **Video wait time (typical)** | PF-2 | Median ≤ 10 min | Median over the same jobs | Same timestamp pair |
| **Time to tell the user about a provider error** | RL-1 | ≤ 60 s from the error | Worst case over injected failures and real errors | Job log: error and user-message timestamps |
| **Regeneration attempts per shot** | QC-2 | ≤ 3 before the shot is reported failed | Max over all shots in a job | Job log: attempts per shot (OB-1) |
| **Delivered shots the automatic check still flags** | VR-1 (proxy) | ≤ 2 per video, target 0 | Per delivered video, worst of the 12 test videos | Job log: check score of each final shot (OB-2) |
| **Cut-time error against the style** | VR-2 | ≤ 0.1 s per cut | Worst cut over every reproduction (EV-2) and every test video (EV-1) | Cut times detected in the finished video vs the style's cut times |

The check-flagged count counts only what the automatic check catches. A shot it misses still counts as fine here, so VR-1 itself stays a reviewer check. The other fidelity rows (VR-3 movement, VR-4 look, VR-5 rooms unchanged, VR-6 transitions) need a person to judge each shot, so they stay reviewer checks in the evals (EV-1, EV-2), not metrics.

## Upstream fixes and open questions

- QC-1 has no final threshold until the first 12 test videos run, and the flagged-shots metric inherits that weakness → set QC-1 after the first run.
- A "download or discard" action on a finished video would give the system a record of whether the photographer kept it → add it as a functional requirement if a success metric is wanted later.
- There is no spend limit (GC-3, user, 2026-10-17), so there is no spend guarantee metric. CO-1 records cost per job → when a limit is set, add it as a requirement row and a "cost per video" metric here.
