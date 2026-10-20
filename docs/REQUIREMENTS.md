# REQUIREMENTS.md — AutoHDR Photo-to-Video

**Status:** draft

**Purpose.** Turn the AutoHDR brief (`docs/AutoHDR Photo to Video.pdf`, "the PRD") and `docs/USERS.md` into testable requirements and constraints with numeric thresholds, so the key-metrics doc can measure against them, the stack doc can choose technology against them and the architecture doc can design to them. Every requirement traces to a use case, a given constraint, or the PRD. The PRD says how submissions are judged: "strong systems engineering, creative problem solving, and consistent professional level output" (PRD p.2). The output must be a video "that does not look AI generated and perfectly adheres to a video style" (p.2).

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

**Assumptions.** USERS.md Section 10 lists the gaps decided without asking, because no one at AutoHDR is available; rows that rest on one say *(assumed)*. Decisions taken after reading `STACK.md` and a PRD audit (2026-10-18) are marked *(assumed, 2026-10-18)*.

**Definitions.**

| Term | Meaning |
|---|---|
| Style | A written description of the look a video should have, plus a song from the Creative Commons list. The text names the pacing and length, the camera movements (by movement name), their speed, the light and photo look, the transitions and the mood, e.g. "Six to eight shots over about 40 s. Open on the exterior with a Drone Top Down Descend. Slow Dolly In through each main room, late-afternoon light with long shadows. Crossfades on the downbeat, hard cuts in the chorus. End on a Dolly Out." Preset styles are saved texts; the photographer can edit one or write their own. A style is text, not a creator's video and not a trained model (0a #8). |
| Shot plan | The per-shot list the system writes for one job from the style text and the photos: for each shot the photo, the photo edit, the movement name and prompt, the speed, the length, the transition and the cut time on the song. The photographer can change it before submitting; it is stored with the job. |
| Shot | One generated clip in a video, the unit that is checked, regenerated and reported as failed. |
| Movement name | One of the PRD's 12 starter-kit movements (PRD pp.8–9): Dolly In, Dolly In (timelapse), Drone Top Down Descend, Timelapse Variant, Dolly Out, Slider Truck Left to Right, Slider Truck Right to Left, Parallax Orbit, Dolly In + Pan Right, Crane Up, Crane Down, Orbit (Hyperlapse). VR-3 compares shots by this name. |
| Visibly AI-generated shot | A shot where a viewer can see warping, morphing, melting or other artifacts. The failing line in USERS.md UC-1. |
| Job | One run of "this photoshoot + this style text + song → this shot plan → this video". |
| Reference video | The video the style's author approved when building the style on its demo photoshoot. It is made by this product, so no third party's video is reused. |
| Reproduction | A job that runs a saved style on another photoshoot so it can be played beside the style's reference video. The PRD's test is "just on a different house" (p.3). |

---

## 0. Requirements summary

| Area | Headline threshold |
|---|---|
| Givens | No spend limit for now; approved providers (free tier for others); due 2026-10-21 |
| Wait | Finished video within 30 min of submitting |
| Quality | ≤ 2 visibly AI shots per video; target 0 |
| Style fidelity | The video follows its shot plan (cuts within ±0.1 s, same movements and transitions); the plan follows the style text; a reproduction looks nearly identical to the reference video |
| Output | 1920×1080, 16:9 |
| Load | 1 job at a time, a second job queued; scaling explained in writing |
| Failures | Never hidden; reported per shot with a reason |

---

## 0a. Key decisions

| # | Decision | Alternative rejected | Where |
|---|---|---|---|
| 1 | The visibly-AI line is the hard fail; song and cut timing are checked but secondary. VR-1's "≤ 2 per video" is the candidate's narrowing of the PRD's "does not look AI generated"; the target stays 0 | Treating all fidelity dimensions as equal | VR-1, VR-2 |
| 2 | The demo is sized for one job at a time; a second job is queued; scaling is written down, not built | Building concurrency now | SC-1, SC-2 |
| 3 | Failed shots are surfaced, not silently replaced | Fallback shots that hide the failure | FR-1.5, RL-2 |
| 4 | Photo edits change composition, lens, angle and light as the PRD asks (pp.3–5), but never architecture, rooms or fixtures | Limiting edits to light and colour | FR-1.8, VR-5 |
| 5 | Styles are authored one way: the author writes the style text and tries it on a demo photoshoot until the result looks right (closest to the PRD's demo-photoshoot example, p.3) | Past-video upload and storyboard-outline methods | FR-2.1 |
| 6 | The web editor (PRD p.7, "optional") is built in v1: swap a room, change a shot, remove a room, re-export, regenerating only the changed shots [src candidate, 2026-10-18: "That was the easiest part"] | Deferring the editor | FR-1.12–FR-1.16, CH-1 |
| 8 | A style is a text description plus a CC song, not a creator's video or a storyboard taken from one, so no creator's video is copied or stored [src candidate, 2026-10-18: "there may be some copyright if we reuse the creator's video … it really should be just a text of the style we are going for"]. This narrows the PRD's "EXACTLY reproduce" (p.3) to "follows the same written style"; the side-by-side test compares with the style's own reference video | Storing a creator's video and its storyboard | FR-1.2, FR-2.1–FR-2.4, VR-2–VR-4 |
| 7 | One shared demo passphrase, no accounts, because a public address with no spend limit lets anyone start paid jobs *(assumed, 2026-10-18)* | Fully open address | FR-3.2, GC-3 |

---

## 1. Givens

### 1.1 Given constraints (GC-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| GC-1 | The submission is complete by **2026-10-21, 11:59 PM local time** *(assumed)* [src U§8] | Dated deliverable in the repo | U§8 | Must |
| GC-2 | One builder; no work depends on another person [src U§8] | Plan names one owner | U§8 | Must |
| GC-3 | No spend limit is set for now; paid use of approved providers is allowed [src user, 2026-10-17: "no budget limits for now"]. A limit may be set later. | Cost per job is recorded (CO-1) | U§8 | Must |
| GC-4 | Every external service is on the approved list (Anthropic, Aqua Voice, Cohere, Cursor, DigitalOcean, ElevenLabs, Google One, Midjourney, OpenAI, OpenRouter, Railway, Vultr, Whisper) or is a free tier of something else [src U§8]. Google models reached through OpenRouter, including with the user's own Google Cloud key (BYOK), count as OpenRouter use *(assumed, 2026-10-18; the user set up BYOK and prefers it)*. | Config review lists each service against the list | U§8 | Gate |
| GC-5 | Used for demo only; every song is an open Creative Commons non-commercial track that allows adaptation (BY-NC or BY-NC-SA, not ND), with its attribution recorded and shown with the video [src U§8]. Every reference video is made by this product with such a track (0a #8). | Each track's licence code and source URL stored in the repo; credit visible on the video page | U§8 | Gate |
| GC-6 | The 12 PRD test photoshoots are the test set [src PRD p.7] | Every eval runs on all 12 | U§8 | Must |
| GC-7 | The submission includes a written explanation of how the system would scale beyond one user at a time [src U§8] | Document exists and is reviewed against SC-2 | U§8 | Must |
| GC-8 | The repo has a README with setup steps, the design in brief and the results on the 12 test shoots, since the PRD judges "systems engineering, creative problem solving" (p.2) [prop] | README review | PRD p.2 | Must |
| GC-9 | The test photoshoots may be sent to the approved video and image providers; they are never committed to the repository, which is public *(assumed, 2026-10-18)* | Repo search finds no test photos; config review | PRD p.7 | Gate |

### 1.2 Dependencies and environment

Not given as inputs beyond GC-3 and GC-4; covered in 3.7.

---

## 2. Functional requirements

*Verified by a user seeing or using the feature at the demo.*

### FR-1 Turn a photoshoot into a video in a chosen style (UC-1)

| ID | Requirement | Trace | Priority |
|---|---|---|---|
| FR-1.1 | The photographer uploads the edited photos of one property in a desktop browser. | F1, U§5 UC-1 | Must |
| FR-1.2 | The photographer sets the style in a text field. Choosing a preset style (from creators or saved by the photographer, PRD p.6) fills the field and its song; the photographer can edit the text, change the song, or write their own. | F2 | Must |
| FR-1.3 | After submitting, the photographer can leave and come back to find the job's status or result. | F3, U§5 UC-1 | Must |
| FR-1.4 | The photographer gets a finished video that follows the style text and its shot plan: the song, shot movements, speeds, transitions and cut timing, on the uploaded photos. | F3, F6 | Must |
| FR-1.5 | If a shot fails after retries, the photographer sees which shot failed and why. The failure is never hidden. A stopped job keeps its finished shots and offers "Start again". | F8 | Must |
| FR-1.6 | When a shot fails, the rest of the video is still delivered without that shot, and the job page marks the failed shot and its reason beside the video *(assumed; reworded 2026-10-18, candidate: "make the best decision")*. A failed shot leaves no gap or placeholder in the video, so a delivered video never shows a broken shot. | F8 | Must |
| FR-1.7 | The photographer never sees a rejected attempt; shots the system itself rejected as visibly AI-generated are regenerated before delivery. | F9, PRD p.2 | Must |
| FR-1.8 | Each shot's photo is improved toward the creator's composition, lens, angle and lighting, as the style's photo edit says (PRD pp.3–5); architecture, rooms and fixtures are preserved. | F7 | Must |
| FR-1.9 | The photographer plays the finished video in the browser and downloads it. | F3 | Must |
| FR-1.10 | From the style text and the photos, the system writes a shot plan: which photos to use and in what order, and for each shot the photo edit, movement, speed, length, transition and cut time. Before submitting, the photographer sees the plan and can change any shot, add one or remove one. If the text asks for a room the photos don't have, the plan says so. | PRD p.3 "the clips they're applied to, the order of the clips, and the cuts to the song are the edits" | Must |
| FR-1.11 | The photographer sees a list of their jobs with status and can reopen any of them. | F3, FR-1.3 | Must |
| FR-1.12 | The photographer can redo one shot of a finished video without regenerating the others. | PRD p.7, CH-1 | Must |
| FR-1.13 | In the web editor, the photographer swaps the room of a shot by choosing another photo from the photoshoot. | F10, PRD p.7 | Must |
| FR-1.14 | In the web editor, the photographer changes a shot: its camera movement (one of the movement names), speed, movement prompt, photo edit, length or transition. | F10, PRD p.7 | Must |
| FR-1.15 | In the web editor, the photographer removes a room (a shot) from the video, and can put it back before re-exporting. | F10, PRD p.7 | Must |
| FR-1.16 | The photographer re-exports the edited video. Only shots whose photo, movement, speed, prompts or photo edit changed, or whose new length is longer than their clip, are made again; the others are reused, and the video is re-cut to the song. Shots the photographer did not touch never change. | F10, PRD p.7, CH-1 | Must |

### FR-2 Create and reproduce a style (UC-2)

| ID | Requirement | Trace | Priority |
|---|---|---|---|
| FR-2.1 | A style author writes a style: a name, the style text and a song. They try it on a demo photoshoot, see the shot plan and the video, and revise the text until it looks right. No video from outside the product is uploaded or reused. | F4, PRD p.3 | Must |
| FR-2.2 | A style is saved as a preset with its name, text and song, and marks one of its videos as the reference video. | F4, F5 | Must |
| FR-2.3 | Running a saved style on any other photoshoot produces a reproduction. | F5, PRD p.3 | Must |
| FR-2.4 | The author plays the reference video beside a reproduction on a different photoshoot. The comparison lists the song, the number and length of shots, the movements and transitions used, and any flagged shot, for both videos. | F5, PRD p.3 | Must |
| FR-2.5 | A saved style can be applied to a different photoshoot, and the photographer can save their own edited text as a new style. | F6, PRD p.6 | Must |

### FR-3 Out of v1 by design

| ID | Requirement | Trace | Priority |
|---|---|---|---|
| FR-3.2 | No accounts. The product is behind one shared demo passphrase (0a #7). | U§7 | Must |
| FR-3.3 | No creator ratings, reviews, payments or credits *(assumed)*. | U§7 | Must |
| FR-3.4 | No phone layout; desktop only. | U§7 | Must |
| FR-3.5 | No past-video upload or storyboard-outline authoring method in v1 (0a #5). | U§6 | Must |
| FR-3.6 | No creator's video, or anything extracted from one, is uploaded, stored or reused (0a #8). | 0a #8 | Gate |

---

## 3. Non-functional requirements

*Absent groups: Authorization (no accounts), Contracts and interfaces (no external consumers), Compliance beyond GC-5 and GC-9, Deployment.*

### 3.1 Verification / correctness (VR-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| VR-1 | At most **2** visibly AI-generated shots per delivered video; target **0** [src user, 2026-10-17; narrows PRD p.2 "does not look AI generated", 0a #1]. | Reviewer watches all 12 test videos and counts failing shots; pass = every video ≤ 2 | FR-1.4 | Must |
| VR-2 | Every video uses its style's song, and its cuts land within **±0.1 s** of the shot plan's cut times [prop] | Detect cut times in every finished video and compare with its plan | FR-1.4, FR-2.3 | Must |
| VR-3 | **100%** of shots move as their plan says (movement name, speed, direction), and **100%** of the movements, transitions and pacing the style text names appear in the plan [src PRD p.3 "down to … the movement of the shots"] | Reviewer labels movement per shot; reviewer checks each plan against its text | FR-1.4, FR-1.10 | Must |
| VR-4 | Overall look of a reproduction versus the style's reference video, "nearly identical … just on a different house" [src PRD p.3]: threshold [tbd: set on the first side-by-side review]; interim target **100%** of reproductions judged a match, floor **80%** [prop] | Side-by-side review by the builder, reference vs reproductions on 2 other shoots | FR-2.4 | Must |
| VR-5 | **0** generated shots or edited photos add, remove or change a room, fixture or architectural feature compared with the source photo [src PRD prompt kit pp.10–12, "Preserve all architectural and interior details", taken as a product rule by the candidate] | Reviewer compares each shot with its photo on the 12 test shoots | FR-1.8 | Must |
| VR-6 | **100%** of transitions in the video match the shot plan (cut, crossfade or other) [src PRD p.3 "all the same effects"] | Compare transitions per cut with the plan | FR-1.4 | Must |

### 3.2 Performance (PF-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| PF-1 | A finished video is available within **30 min** of submitting a job, including every shot regeneration [src user, 2026-10-17]. | Time 12 test jobs from submit to playable; max ≤ 30 min | FR-1.3, FR-1.4 | Must |
| PF-2 | Typical jobs finish within **10 min**; 30 min is the limit, not the aim [src user: "10–30 min is perfectly fine"]. | Median job time over the 12 test jobs | FR-1.3 | Should |
| PF-3 | Generation time and regeneration time share the 30 min of PF-1; regeneration may use at most **the remainder** after the first pass. | Job log shows first-pass and regeneration time sum ≤ 30 min | FR-1.7 | Must |
| PF-4 | A re-export from the editor with up to 2 changed shots is playable within **10 min** [prop]. | Time re-exports on 3 test videos | FR-1.16 | Should |

### 3.3 Reliability and failure modes (RL-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| RL-1 | A provider error or a usage or rate limit is reported to the user within **60 s** of occurring [prop]. | Inject a failing provider; time the message | FR-1.5 | Must |
| RL-2 | **100%** of failed shots appear in the result with a reason; none are replaced silently [src user, 2026-10-17: "just show the failure"]. | Inject a failing shot; result lists it | FR-1.5 | Must |
| RL-3 | A failed shot never stops the other shots in the job from finishing *(assumed)*. | Inject one failure in a job; remaining shots complete | FR-1.6 | Must |

### 3.4 Observability (OB-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| OB-1 | Every job records its style, each shot's photo, photo-edit prompt, video prompt, model, number of attempts and pass/fail result, and total time [prop]. | Inspect the log of a test job | VR-1, PF-1 | Must |
| OB-2 | Every shot a quality check rejected is recorded with the check's score [prop]. | Inspect the log | FR-1.7 | Should |

### 3.5 Quality checks (QC-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| QC-1 | An automatic check flags visibly AI-generated shots and changed rooms or fixtures; threshold [tbd: judged on the first 12 test videos; interim target: catches ≥ 60% of shots the reviewer fails [prop]] [src user: "ideally the ml model catch it"; PRD p.2 "consistent professional level output"]. | Compare flagged shots to the reviewer's list | FR-1.7 | Must |
| QC-2 | A shot gets up to **4** attempts per round (the first plus 3 regenerations) before it is reported failed [prop]. | Job log shows attempts ≤ 4 per shot per round | FR-1.5, FR-1.7 | Must |

### 3.6 Scalability (SC-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| SC-1 | Supports **1** job at a time [src user, 2026-10-17]. A second job submitted while one runs is queued, and the photographer sees that it is waiting. | Submit two jobs; the second waits and then runs; the first is unaffected | GC-7 | Must |
| SC-2 | The written scaling explanation states what changes to run N jobs at once, with each job still within PF-1 and outputs unchanged [src user]. | Review of the explanation | GC-7 | Must |

### 3.7 Environment and output (DE-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| DE-1 | Works in the current desktop Chrome release [prop]. | Run all FR-1 steps in Chrome | FR-3.4 | Must |
| DE-2 | Uploads accept **JPG and PNG**, up to **40 photos** and **25 MB each** [prop]. | Upload a set of 40 photos at 25 MB | FR-1.1 | Must |
| DE-3 | The demo runs end to end on the builder's machine or hosted APIs without a GPU requirement *(assumed)*. | Clean-install run | U§8 | Should |
| DE-4 | The demo runs live if a job finishes within the demo's time window; otherwise a pre-generated job is shown [src user]. | Both modes rehearsed before the deadline | PF-1 | Must |
| DE-5 | The finished video is **1920×1080, 16:9 landscape**, at the style's frame rate (24 or 30 fps, set with the style) [prop; PRD p.2 "professional level output"]. | Inspect the file of each test video | FR-1.9 | Must |

### 3.8 Evaluation suite (EV-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| EV-1 | One eval runs at least one demo style on each of the 12 test photoshoots and reports, per video, the count of visibly AI shots, rooms changed, cut-time error and the job time [prop]. | Report exists and covers 12 videos | VR-1, VR-2, VR-5, PF-1 | Must |
| EV-2 | One eval runs each preset style on at least 2 test shoots other than its demo shoot, and reports VR-2, VR-3, VR-4 and VR-6 against the reference video and the plans [prop]. | Report exists per style and shoot | VR-2, VR-3, VR-4, VR-6 | Must |

### 3.9 Cost (CO-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| CO-1 | Every job records the cost of each provider call and the job's total, so a spend limit set later can be enforced [prop]. Where the provider bills the user directly (BYOK) and returns no cost, the call records seconds × list price. Nothing is blocked on cost now. A call to a service outside the approved list stops and says so when its free tier runs out (GC-4). | Inspect the log of a test job; run one outside-list call past its free limit | GC-3, GC-4 | Should |

### 3.10 Change and later iterations (CH-)

| ID | Requirement | Verified by | Trace | Priority |
|---|---|---|---|---|
| CH-1 | A finished job's shots, their order and their cut times are stored, so the editor can swap, change or remove one shot without regenerating the others [prop]. | Inspect a stored job; it lists each shot separately; an edit of one shot leaves the others' clips unchanged | F10 | Must |
| CH-2 | Two jobs can run at once without changing outputs once capacity is added, with 0 changes to a style [prop]. | Run two jobs with the same style on separate capacity; outputs match single-job runs | U§6 later #2 | Should |

---

## 4. Traceability matrix

| Requirement group | UC-1 | UC-2 | Source |
|---|---|---|---|
| Givens (GC) | ✓ | ✓ | USERS.md §8; PRD pp.2, 7 |
| Functional (FR) | ✓ | ✓ | USERS.md §6; PRD pp.3, 6, 7 |
| Verification (VR) | ✓ | ✓ | PRD pp.2, 3, 10–12; user |
| Performance (PF) | ✓ | | user |
| Reliability (RL) | ✓ | | user |
| Observability (OB) | ✓ | | |
| Quality checks (QC) | ✓ | | user; PRD p.2 |
| Scalability (SC) | ✓ | | user |
| Environment and output (DE) | ✓ | ✓ | user; PRD p.2 |
| Evaluation (EV) | ✓ | ✓ | PRD p.3 |
| Cost (CO) | ✓ | ✓ | GC-3 |
| Change (CH) | UC-3 | | USERS.md §6; PRD p.7 |

---

## 5. Proposed thresholds

Every **[prop]** and **[tbd]** number. [prop] rows not commented on at review are accepted; [tbd] rows stay pending.

| Row | Value | Reasoning | Status |
|---|---|---|---|
| VR-2 | cuts within ±0.1 s | About 2–3 frames at 24–30 fps, below what a viewer sees as off-beat | Accepted |
| VR-4 | [tbd]; interim 100% of shots match, floor 80% | The PRD says "EXACTLY reproduce" and "nearly identical"; set on the first side-by-side review | Pending prototype |
| RL-1 | 60 s | Long enough for a retry, short enough to feel responsive | Accepted |
| OB-1, OB-2 | listed fields | Needed to run EV-1 and EV-2 | Accepted |
| QC-1 | [tbd]; interim ≥ 60% of failing shots caught | The number depends on the detector | Pending prototype |
| QC-2 | 4 attempts per round | Bounded so regeneration stays inside PF-1 | Accepted |
| DE-1 | current desktop Chrome | User said assume desktop | Accepted |
| DE-2 | JPG/PNG, 40 photos, 25 MB | Covers a typical shoot with room to spare; the 12 test shoots set the real size | Accepted |
| PF-4 | re-export ≤ 10 min for ≤ 2 changed shots | One round of a few clips in parallel plus a re-cut, measured at about 1–2 min per clip (VIDEO_RESEARCH §7) | Proposed 2026-10-18 |
| DE-5 | 1920×1080, 16:9, the style's frame rate | Listing videos are landscape HD; Veo 3.1 costs the same at 720p and 1080p (STACK §6) | Proposed 2026-10-18 |
| GC-8 | README with setup, design, results | The PRD judges engineering and problem solving | Proposed 2026-10-18 |
| CO-1 | cost recorded per call and per job; list price for BYOK | No spend limit now (user, 2026-10-17); recording lets one be added | Accepted |
| EV-1, EV-2 | reports listed | Needed to verify VR rows | Accepted |
| CH-1, CH-2 | as written | Later iterations 1 and 2 need them | Accepted |

**Open items only a running system (or an upstream fix) can answer:**
1. Which approved or free-tier models can produce shots that are not visibly AI-generated, and how long they take (decides PF-1 and QC-2). First results: `VIDEO_RESEARCH.md` §7.
2. What "nearly identical" means on a real side-by-side of a reference video and a reproduction (VR-4), and whether a written style is precise enough to get there (0a #8).
3. Which usage or rate limits the 12 test jobs hit, and what the 12 jobs cost (CO-1). If a spend limit is set later, add its row.
4. Whether photo edits that change angle and lens keep architecture intact often enough (VR-5); if not, the edit narrows per shot and the narrowing is recorded.
