# REQUIREMENTS.md — AutoHDR Photo-to-Video

**Status:** draft

**Purpose.** Turn the AutoHDR brief (`docs/AutoHDR Photo to Video.pdf`, "the PRD") and `docs/USERS.md` into testable requirements and constraints with numeric thresholds, so the key-metrics doc can measure against them, the stack doc can choose technology against them and the architecture doc can design to them. Every requirement traces to a use case, a given constraint, or the PRD.

**Scope.**

*This document decides:* what the system must do per use case in the minimum product (USERS.md Section 6, features F1–F9; later iterations get rows when they enter a build), the "must never" rules, numeric thresholds for quality attributes, how each is verified, and what is out of scope by design.

*This document defers:*
- Technology choices, including which video and image models → the stack document.
- Modules, data flow, and the techniques used to meet a budget → the architecture document.
- Why the problem exists and who the user is → USERS.md (cited, not restated).
- Which requirements become tracked metrics → the key-metrics document.

If a row names a library, a component, or a way of meeting a threshold, it is in the wrong document.

**How to read a requirement.** Functional rows (ID · Requirement · Trace · Priority) say what the user does or expects, with no number; a user seeing the feature at the demo verifies them. Non-functional and given rows (ID · Requirement · Verified by · Trace · Priority) are the number itself, tagged. Priority: **Gate** = must hold before real data; **Must** = required for the product to be done; **Should** = required unless a documented tradeoff says otherwise. This document does not cut scope for the deadline.

**Where the numbers come from.** **[src]** = from the PRD, USERS.md or the user's own answers (cited), or computed from one. **[prop]** = proposed target; reviewable. **[tbd]** = cannot be set until a prototype exists. Section 5 lists every [prop] and [tbd].

**Assumptions.** USERS.md Section 10 lists the gaps decided without asking, because no one at AutoHDR is available; rows that rest on one say *(assumed)*.

**Definitions.**

| Term | Meaning |
|---|---|
| Style | A stored storyboard of shots: for each shot a camera-movement description, its place in the song and its cut time, plus the song itself. Reproduced on a new photoshoot to make a video. |
| Shot | One generated clip in a video, the unit that is checked, regenerated and reported as failed. |
| Visibly AI-generated shot | A shot where a viewer can see warping, morphing, melting or other artifacts. The failing line in USERS.md UC-1. |
| Job | One run of "this photoshoot + this style → this video". |
| Reproduction | A job run on the creator's own demo photoshoot, compared side by side with the original video. |

---

## 0. Requirements summary

| Area | Headline threshold |
|---|---|
| Givens | No spend limit for now; approved providers (free tier for others); due 2026-10-21 |
| Wait | Finished video within 30 min of submitting |
| Quality | ≤ 2 visibly AI shots per video; target 0 |
| Style fidelity | Same song; cuts within ±0.1 s; same movement type per shot |
| Load | 1 job at a time; scaling explained in writing |
| Failures | Never hidden; reported per shot with a reason |

---

## 0a. Key decisions

| # | Decision | Alternative rejected | Where |
|---|---|---|---|
| 1 | The visibly-AI line is the hard fail; song and cut timing are checked but secondary | Treating all fidelity dimensions as equal | VR-1, VR-2 |
| 2 | The demo is sized for one job at a time; scaling is written down, not built | Building concurrency now | SC-1, SC-2 |
| 3 | Failed shots are surfaced, not silently replaced | Fallback shots that hide the failure | FR-1.5, RL-2 |

---

## 1. Givens

### 1.1 Given constraints (GC-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| GC-1 | The submission is complete by **2026-10-21, 11:59 PM local time** *(assumed)* [src U§8] | Dated deliverable in the repo | U§8 | Must |
| GC-2 | One builder; no work depends on another person [src U§8] | Plan names one owner | U§8 | Must |
| GC-3 | No spend limit is set for now; paid use of approved providers is allowed [src user, 2026-10-17: "no budget limits for now"]. A limit may be set later. | Cost per job is recorded (CO-1) | U§8 | Must |
| GC-4 | Every external service is on the approved list (Anthropic, Aqua Voice, Cohere, Cursor, DigitalOcean, ElevenLabs, Google One, Midjourney, OpenAI, OpenRouter, Railway, Vultr, Whisper) or is a free tier of something else [src U§8] | Config review lists each service against the list | U§8 | Gate |
| GC-5 | Used for demo only; every song is an open Creative Commons non-commercial track, with its attribution recorded [src U§8] | Each track's license and source URL stored in the repo | U§8 | Gate |
| GC-6 | The 12 PRD test photoshoots are the test set [src PRD p.7] | Every eval runs on all 12 | U§8 | Must |
| GC-7 | The submission includes a written explanation of how the system would scale beyond one user at a time [src U§8] | Document exists and is reviewed against SC-2 | U§8 | Must |

### 1.2 Dependencies and environment

Not given as inputs beyond GC-3 and GC-4; covered in 3.4.

---

## 2. Functional requirements

*Verified by a user seeing or using the feature at the demo.*

### FR-1 Turn a photoshoot into a video in a chosen style (UC-1)

| ID | Requirement | Trace | Priority |
|---|---|---|---|
| FR-1.1 | The photographer uploads the edited photos of one property in a desktop browser. | F1, U§5 UC-1 | Must |
| FR-1.2 | The photographer picks a style from a library of styles. | F2 | Must |
| FR-1.3 | After submitting, the photographer can leave and come back to find the job's status or result. | F3, U§5 UC-1 | Must |
| FR-1.4 | The photographer gets a finished video that follows the chosen style: the style's song, shot movements and cut timing, on the uploaded photos. | F3, F6 | Must |
| FR-1.5 | If a shot fails after retries, the photographer sees which shot failed and why. The failure is never hidden. | F8 | Must |
| FR-1.6 | When a shot fails, the rest of the video is still delivered with the failed shot marked *(assumed)*. | F8 | Must |
| FR-1.7 | The photographer never sees a rejected attempt; shots the system itself rejected as visibly AI-generated are regenerated before delivery. | F9 | Should |
| FR-1.8 | Each shot shows its photo improved toward the creator's composition, lens, angle and lighting, with the property's rooms and fixtures unchanged. | F7 | Must |
| FR-1.9 | The photographer plays the finished video in the browser and downloads it. | F3 | Must |

### FR-2 Create and reproduce a style (UC-2)

| ID | Requirement | Trace | Priority |
|---|---|---|---|
| FR-2.1 | A style can be created through the product by at least one method (demo shoot, past-video upload, or storyboard outline) *(assumed)*. | F4 | Must |
| FR-2.2 | A created style is saved in the library with a name and its song. | F4, F5 | Must |
| FR-2.3 | Running a style on its own demo photoshoot produces a reproduction. | F5 | Must |
| FR-2.4 | The creator plays the original video and its reproduction side by side. | F5 | Must |
| FR-2.5 | A saved style can be applied to a different photoshoot. | F6 | Must |

### FR-3 Out of v1 by design

| ID | Requirement | Trace | Priority |
|---|---|---|---|
| FR-3.1 | No web editor for swapping, changing or removing shots; see later iteration 1 (UC-3). | U§6 later #1 | Must |
| FR-3.2 | No accounts or logins; the product is open for the demo. | U§7 | Must |
| FR-3.3 | No creator ratings, reviews, payments or credits *(assumed)*. | U§7 | Must |
| FR-3.4 | No phone layout; desktop only. | U§7 | Must |

---

## 3. Non-functional requirements

*Absent groups: Authorization (no accounts, demo-open), Contracts and interfaces (no external consumers), Compliance beyond GC-5, Deployment.*

### 3.1 Verification / correctness (VR-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| VR-1 | At most **2** visibly AI-generated shots per delivered video; target **0** [src user, 2026-10-17]. | Reviewer watches all 12 test videos and counts failing shots; pass = every video ≤ 2 | FR-1.4 | Must |
| VR-2 | A reproduction uses the original's song and its cut times within **±0.1 s** [prop] | Compare cut timestamps of original and reproduction for each demo style | FR-2.3, FR-2.4 | Must |
| VR-3 | In a reproduction, **100%** of shots use the same movement type as the original's matching shot [prop] | Reviewer labels movement type per shot in both videos | FR-2.3 | Must |
| VR-4 | Overall look of a reproduction versus the original, "nearly identical" [src PRD p.3]: threshold [tbd: set on the first side-by-side review of a demo style]; interim build target: reviewer says it passes for ≥ 80% of shots [prop] | Side-by-side review by the builder | FR-2.4 | Must |
| VR-5 | **0** generated shots add, remove or change a room, fixture or architectural feature compared with the source photo [src PRD p.10] | Reviewer compares each shot with its photo on the 12 test shoots | FR-1.8 | Must |

### 3.2 Performance (PF-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| PF-1 | A finished video is available within **30 min** of submitting a job, including every shot regeneration [src user, 2026-10-17]. | Time 12 test jobs from submit to playable; max ≤ 30 min | FR-1.3, FR-1.4 | Must |
| PF-2 | Typical jobs finish within **10 min**; 30 min is the limit, not the aim [src user: "10–30 min is perfectly fine"]. | Median job time over the 12 test jobs | FR-1.3 | Should |
| PF-3 | Generation time and regeneration time share the 30 min of PF-1; regeneration may use at most **the remainder** after the first pass. | Job log shows first-pass and regeneration time sum ≤ 30 min | FR-1.7 | Must |

### 3.3 Reliability and failure modes (RL-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| RL-1 | A provider error or a usage or rate limit is reported to the user within **60 s** of occurring [prop]. | Inject a failing provider; time the message | FR-1.5 | Must |
| RL-2 | **100%** of failed shots appear in the result with a reason; none are replaced silently [src user, 2026-10-17: "just show the failure"]. | Inject a failing shot; result lists it | FR-1.5 | Must |
| RL-3 | A failed shot never stops the other shots in the job from finishing *(assumed)*. | Inject one failure in a job; remaining shots complete | FR-1.6 | Must |

### 3.4 Observability (OB-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| OB-1 | Every job records its style, each shot's prompt, model, number of attempts and pass/fail result, and total time [prop]. | Inspect the log of a test job | VR-1, PF-1 | Must |
| OB-2 | Every shot a quality check rejected is recorded with the check's score [prop]. | Inspect the log | FR-1.7 | Should |

### 3.5 Quality checks (QC-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| QC-1 | An automatic check flags visibly AI-generated shots; threshold [tbd: judged on the first 12 test videos; interim target: catches ≥ 60% of shots the reviewer fails [prop]] [src user: "ideally the ml model catch it"]. | Compare flagged shots to the reviewer's list | FR-1.7 | Should |
| QC-2 | A flagged shot is regenerated up to **3** times before it is reported failed [prop]. | Job log shows attempts ≤ 3 per shot | FR-1.5, FR-1.7 | Should |

### 3.6 Scalability (SC-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| SC-1 | Supports **1** job at a time [src user, 2026-10-17]. A second job submitted while one runs is queued or refused with a message. | Submit two jobs; second does not break the first | GC-7 | Must |
| SC-2 | The written scaling explanation states what changes to run N jobs at once, with each job still within PF-1 and outputs unchanged [src user]. | Review of the explanation | GC-7 | Must |

### 3.7 Environment (DE-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| DE-1 | Works in the current desktop Chrome release [prop]. | Run all FR-1 steps in Chrome | FR-3.4 | Must |
| DE-2 | Uploads accept **JPG and PNG**, up to **40 photos** and **25 MB each** [prop]. | Upload a set of 40 photos at 25 MB | FR-1.1 | Must |
| DE-3 | The demo runs end to end on the builder's machine or hosted APIs without a GPU requirement *(assumed)*. | Clean-install run | U§8 | Should |
| DE-4 | The demo runs live if a job finishes within the demo's time window; otherwise a pre-generated job is shown [src user]. | Both modes rehearsed before the deadline | PF-1 | Must |

### 3.8 Evaluation suite (EV-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| EV-1 | One eval runs at least one demo style on each of the 12 test photoshoots and reports, per video, the count of visibly AI shots and the job time [prop]. | Report exists and covers 12 videos | VR-1, PF-1 | Must |
| EV-2 | One eval runs each demo style on its own demo photoshoot and reports VR-2 through VR-4 [prop]. | Report exists per style | VR-2, VR-3, VR-4 | Must |

### 3.9 Cost (CO-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| CO-1 | Every job records the cost of each provider call and the job's total, so a spend limit set later can be enforced [prop]. Nothing is blocked on cost now. A call to a service outside the approved list stops and says so when its free tier runs out (GC-4). | Inspect the log of a test job; run one outside-list call past its free limit | GC-3, GC-4 | Should |

### 3.10 Change and later iterations (CH-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| CH-1 | A finished job's shots, their order and their cut times are stored, so a later editor could swap or remove one shot without regenerating the others [prop]. | Inspect a stored job; it lists each shot separately | U§6 later #1 | Should |
| CH-2 | Two jobs can run at once without changing outputs once capacity is added, with 0 changes to a style [prop]. | Run two jobs with the same style on separate capacity; outputs match single-job runs | U§6 later #2 | Should |

---

## 4. Traceability matrix

| Requirement group | UC-1 | UC-2 | Source |
|---|---|---|---|
| Givens (GC) | ✓ | ✓ | USERS.md §8 |
| Functional (FR) | ✓ | ✓ | USERS.md §6 |
| Verification (VR) | ✓ | ✓ | PRD pp.3, 10; user |
| Performance (PF) | ✓ | | user |
| Reliability (RL) | ✓ | | user |
| Observability (OB) | ✓ | | |
| Quality checks (QC) | ✓ | | user |
| Scalability (SC) | ✓ | | user |
| Environment (DE) | ✓ | ✓ | user |
| Evaluation (EV) | ✓ | ✓ | |
| Cost (CO) | ✓ | ✓ | GC-3 |
| Change (CH) | UC-3 (later) | | USERS.md §6 |

---

## 5. Proposed thresholds

Every **[prop]** and **[tbd]** number. [prop] rows not commented on at review are accepted; [tbd] rows stay pending.

| Row | Value | Reasoning | Status |
|---|---|---|---|
| VR-2 | cuts within ±0.1 s | About 3 frames at 30 fps, below what a viewer sees as off-beat | Accepted |
| VR-3 | 100% same movement type | The PRD says movements must be reproduced "down to" the shot movement | Accepted |
| VR-4 | [tbd]; interim ≥ 80% of shots pass | "Nearly identical" is not a number; set on the first side-by-side review | Pending prototype |
| RL-1 | 60 s | Long enough for a retry, short enough to feel responsive | Accepted |
| OB-1, OB-2 | listed fields | Needed to run EV-1 and EV-2 | Accepted |
| QC-1 | [tbd]; interim ≥ 60% of failing shots caught | User wants the check "if possible"; the number depends on the detector | Pending prototype |
| QC-2 | 3 attempts | Bounded so regeneration stays inside PF-1 | Accepted |
| DE-1 | current desktop Chrome | User said assume desktop | Accepted |
| DE-2 | JPG/PNG, 40 photos, 25 MB | Covers a typical shoot with room to spare; the 12 test shoots set the real size | Accepted |
| CO-1 | cost recorded per call and per job; no limit enforced | No spend limit now (user, 2026-10-17); recording lets one be added | Accepted |
| EV-1, EV-2 | reports listed | Needed to verify VR rows | Accepted |
| CH-1, CH-2 | as written | Later iterations 1 and 2 need them | Accepted |

**Open items only a running system (or an upstream fix) can answer:**
1. Which approved or free-tier models can produce shots that are not visibly AI-generated, and how long they take (decides PF-1 and QC-2).
2. What "nearly identical" means on a real side-by-side (VR-4).
3. Which usage or rate limits the 12 test jobs hit, and what the 12 jobs cost (CO-1). If a spend limit is set later, add its row.
