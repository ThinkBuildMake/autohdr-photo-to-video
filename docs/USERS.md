# USERS.md — AutoHDR Photo-to-Video

## Scope

**This document covers:** who the product is for and who it is not for; what goes wrong for them today, with sources; the moment the product enters their day; the use cases it serves and why this shape of product is the one they'd choose; the minimum first iteration and the features that come after; what is out of scope; and the constraints the project was given.

**This document does not cover:** how the product is built, verified, measured or hosted. Requirements, key metrics, stack and architecture are separate documents that trace back to the use case IDs (UC-n) and the constraints here.

**Status:** draft, interview on 2026-10-16/17. The only source is the AutoHDR hackathon brief (`docs/AutoHDR Photo to Video.pdf`, cited as "the PRD"); no one at AutoHDR has been interviewed. The problem is taken as given by AutoHDR. The person's day in Section 4 is an illustrative composite, not an observed customer. Where the interview left a gap, this document states an assumption (Section 10) so downstream work can proceed; each assumption is marked *(assumed)* where it is used.

---

## 1. Target user

**A novice photographer who runs a small real-estate photography company, delivers edited property photos to real-estate agents, and is now expected to deliver video as well.** They already edit photos in AutoHDR *(PRD: AutoHDR's customers are professional real-estate photographers)*.

Per the PRD, agents expect photographers to shoot video as well as photos, and video is "HARD": it takes years to learn shooting and editing, and novices have to be trained on gimbals, complex movements and creative editing. The novice is responsible for handing the agent a video that looks like the work of a top videographer, without having the skills, gear or lighting conditions that produce it. *(All of this is AutoHDR's account; it is not verified by us.)*

**Not the target user:**
- **The top creative videographer** (the PRD's example is JT Visuals) who builds a style. They supply styles the novice picks from. They are not who the product is designed around, though the product needs a way for a style to get made (UC-2).
- **The agent or homeowner** who views the finished video and sometimes asks for revisions. They never use the product directly.

---

## 2. The problem, in numbers

The problem is taken as given by AutoHDR, and the evidence we could find is thin. The numbers below show that video matters to agents and that outsourced editing costs money. They do not show how many novice photographers struggle with video, or how much it costs them.

### Agents want video, according to one survey

HomeJab's agent survey (2021) found 36% of agents preferred video tours over 3D tours (21%) and 30% used both depending on the seller [1]. A secondary write-up of Realtors® data says video and 3D tour orders rose from 37% to 54% in 2020 and fell to 48% in 2021 [2].

### Outsourced video editing has a price, according to vendors

Vendor pages list outsourced real-estate video editing at roughly $30–$150 per video, with individual vendors listing $140 and $278 [3]. These are sellers' own prices; we did not find an independent source.

### Tools already exist in this space

Animoto (general slideshow maker, about $30/month entry paid price), Runway (generates camera motion from stills, from about $12/month) and listing-specific makers such as AutoReel (about $59/month entry paid price) and Reel-E.ai ($44–$599/month) all take listing photos and make video [4]. We took these prices from comparison and vendor pages, not each vendor's own pricing page, so plan caps and credit metering are unchecked.

---

## 3. Why we target the moment after the shoot

The product enters one phase of the novice's day: **after the photos are edited and an agent is waiting for a video**. It does not target shooting video on site, which is where the PRD says novices lack gear, movement skills and lighting.

The goal, in the novice's terms, is a video the agent would accept as work from a top videographer, produced without the novice shooting or editing any footage.

**Reason 1: The novice's gap is creative vision, not effort (AutoHDR's claim).** The PRD says even with months or years of training most photography companies "don't achieve the level of excellence from the top videographers," and that they spend thousands of dollars on courses and flying trainers in without matching it. We have no independent source for this.

**Reason 2: Plain AI output is visibly AI.** The PRD says that taking an edited photo and animating it directly "would make it obvious it's an AI video," and that the goal is output indistinguishable from a professional videographer's. This is AutoHDR's observation.

### Out of scope: shooting and training

How to shoot video on site, how to use a gimbal, and how to train staff are different work at a different moment. They are out of scope.

---

## 4. Workflow: where the product enters the day

*Illustrative composite, built from the PRD. Dana and the times are invented to walk the flow.*

**Tuesday, 6:40 PM.** Dana, who runs a two-person photography company, just finished editing 28 photos of a four-bedroom house for an agent. The agent texted at noon: "Can I get a video for the listing too?" Dana has never shot a gimbal walkthrough and has no editor.

**The 30 seconds before opening it:** Dana doesn't know whether any video she can make would look good enough to send, and has no idea which style the agent would like.

**What they need from it:** a way to pick a style from a creator Dana trusts, upload the 28 photos, and walk away. → **UC-1**

**What they do with the output:** Dana watches the finished video, sends it to the agent if it looks professional, and notices any shot that looks fake. If the agent asks to swap a room, Dana wants to change just that. → **UC-1**, later **UC-3**

**Behind the scenes:** a top videographer once built the style Dana picked, by choosing shot movements, a song and the cut timing. → **UC-2**

---

## 5. Use cases

### UC-1: Turn a finished photoshoot into a video in a chosen style

| | |
|---|---|
| **Trigger** | The photographer has edited photos for a listing and wants a video for the agent. |
| **Input** | The edited photos from one property; a style picked from a library (a creator's, or one the photographer saved). |
| **What they need to see** | A finished video that follows the chosen style (the same camera movements, song and cut timing as the original, on this house) and that does not look AI-generated. If any shot failed, which shot and why. |
| **What they do with it** | Watch it, decide whether it is good enough for the agent, and send it. The product never sends it to the agent for them. |
| **Time available** | 10–30 minutes of waiting is acceptable to them (their own answer for this project); they come back when it is done. |
| **Must never** | Show a shot that looks visibly AI-generated as if it were fine; hide a failed shot; present a video as the creator's style when it isn't. |

**Why a style-driven generator, not a slideshow tool or a hired editor:**
A template tool can cut photos to a song, and a freelance editor can match a style if given footage. Neither does what this user needs.

1. **The inputs are photos, not footage.** The movement in the finished video has to be generated; a slideshow only pans and zooms.
2. **The photos are mediocre.** The PRD wants composition, angle, lens and lighting changed toward how the creator would have shot it, and a slideshow keeps the photo as it is.
3. **The target is one specific creator's video.** The PRD wants the same movements, song and cuts reproduced so the original and the new video "look nearly identical, just on a different house." A generic template does not do that.

This case depends on the generated shots passing as professional work; that is untested. If they don't, a slideshow tool with a creator's song and pacing would be the honest alternative.

---

### UC-2: A style gets created and reproduced

| | |
|---|---|
| **Trigger** | A creator (or whoever builds styles on their behalf) wants a video they made to become a reusable style. |
| **Input** | The creative decisions behind a video made from a demo photoshoot: the shots, their movements, the song, the cut timing. |
| **What they need to see** | The style saved in the library and a generated video from a demo shoot that matches the original side by side. |
| **What they do with it** | Judge whether the reproduction is close enough to publish the style. |
| **Time available** | Not time-critical; the creator judges the reproduction once per style *(assumed)*. |
| **Must never** | Reproduce a style in a way that visibly differs from the original in song, movement or cuts without saying so. |

This use case serves UC-1: without a style, there is nothing for the novice to pick. Which authoring method to build (demo shoot, past-video upload, storyboard outline, per the PRD) is a design decision; the minimum is that one method works end to end *(assumed)*.

**Why a stored, reusable style, not rebuilding each video by hand:** a creator spent hours on the original video, and the point of the product is that no one repeats that for the next house. Reproduction has to be repeatable.

---

### UC-3: Revise a finished video (later iteration)

The PRD describes an optional web editor for swapping a room, changing a shot or removing a room, because agents and homeowners "often have subjective revision requests." It is not in the first iteration; see Section 6.

---

## 6. The minimum product

**First iteration.** The minimum is the PRD's end-to-end flow: a novice uploads photos, picks a style, and gets back a finished video that matches the style and does not look AI-generated, with failures shown instead of hidden. This is the thing the owner would open on a Tuesday, because without style reproduction the product is a slideshow tool.

| # | Feature | Use case | What it does for the user | Acceptable in v1 |
|---|---|---|---|---|
| F1 | Upload a property photoshoot | UC-1 | Gives the product the photos | Desktop browser only; one user at a time; demo-open, no login |
| F2 | Pick a style from a library | UC-1 | Chooses whose look the video gets | Library of the styles built for the demo |
| F3 | Receive a finished video | UC-1 | Gets a video with no editing work | Wait of 10–30 minutes is fine; follows the chosen style |
| F4 | Create a style | UC-2 | Turns a creator's video into a reusable style | At least one authoring method works end to end; 2–3 demo styles *(assumed)* |
| F5 | Capture the style's decisions and reproduce them | UC-2 | The reproduction looks nearly identical to the original side by side | A shot that looks visibly AI-generated is the failing line; 1–2 per demo video are tolerated, zero is the target |
| F6 | Apply a saved style to a new photoshoot | UC-1, UC-2 | Same movements, song and cuts on a different house | Tested on the 12 sample photoshoots |
| F7 | Improve mediocre photos toward the creator's composition, lens, angle and lighting | UC-1 | Makes a novice's photo look like the creator's shot | Same "visibly AI" line; photo content (rooms, fixtures) must not change *(assumed)* |
| F8 | Show which shot failed and why | UC-1 | Lets the user see a failure instead of a hidden defect | Never hidden; the rest of the video is still delivered with the failed shot marked *(assumed)* |
| F9 | Automatically catch visibly AI-looking shots and regenerate them | UC-1 | Fewer bad shots reach the user | Wanted if possible; v1 may let 1–2 slip through |

The owner's demo can run live if generation is fast enough, and otherwise is shown from a pre-generated run. The owner also expects to be able to explain how it would scale beyond one user at a time.

**Later iterations,** in the order the owner would want them. Later is not out of scope; it's the plan.

| # | Feature | Use case | What it adds for the user | Why not first |
|---|---|---|---|---|
| 1 | Web editor: swap a room, change a shot, remove a room, re-export | UC-3 | Handles agent and homeowner revisions without starting over | The PRD marks it optional; it needs the minimum working first *(assumed not expected for this submission)* |
| 2 | Several photoshoots at once / more than one user | UC-1 | The product holds up beyond a demo | Demo is one user at a time |

---

## 7. Explicitly out of scope

| Not doing | Why |
|---|---|
| Commercial or public launch | The use is demo only |
| Phone use | Desktop assumed |
| Durable storage beyond the demo | Uploads, styles and videos only need to last through the demo *(assumed)* |
| Accounts and logins | Demo-open for now |
| Licensed or commercial music | Any open Creative Commons non-commercial track is acceptable for the demo |
| Shooting video on site, gimbal and team training | Different work at a different moment (Section 3) |
| Creator ratings, reviews, payments or credits | Shown in the PRD's mockups but not in its requirements list *(assumed out)* |

---

## 8. Constraints we were given

Inputs the project arrived with, not choices made while designing it.

| Constraint | What it is | Given by |
|---|---|---|
| Timeline | Due next Wednesday, **2026-10-21**. Time of day and time zone were not given; assume end of day, 11:59 PM, in the candidate's local time *(assumed)*. Deliverable not given; assume a working demo plus the repo *(assumed)*. Nothing is named as dropped first: "try to drop nothing." | The hackathon |
| Team | One person | Candidate |
| Spend | No budget limit for now (candidate, 2026-10-17: "I meant no budget limits for now"). Paid use of approved providers is allowed. Services outside the approved list may be used only on a free tier. Whether AutoHDR reimburses spend, and whether the limit changes later, was not asked. | Candidate |
| Services / vendors | Approved-provider list, a whitelist to choose from: Anthropic, Aqua Voice, Cohere, Cursor, DigitalOcean, ElevenLabs, Google One, Midjourney, OpenAI, OpenRouter, Railway, Vultr, Whisper. Free tiers of anything else are allowed. | The hackathon |
| Hardware in hand | Local or cloud both possible. Specs were not given; assume no GPU is relied on and generation runs through hosted APIs *(assumed)*. | Candidate |
| Intended use | Demo only. Music: any open Creative Commons non-commercial track. | Candidate |
| Test data | 12 test photoshoots, randomly sampled across users, from the Dropbox link in the PRD | The hackathon |
| Scale | One user at a time; the candidate should be able to explain how it would scale | Candidate |

---

## 9. Evidence limitations

- **HomeJab survey [1]:** agents only, 2021, self-reported; says nothing about photographers.
- **Realtors® order figures [2]:** reached through a secondary write-up, 2020–2021 and pandemic-era; two write-ups of the HomeJab study give different percentages (36% and 39%).
- **Outsourcing prices [3]:** vendors' own prices, not independent.
- **Existing tools [4]:** taken from comparison and vendor pages; plan caps and credit metering were not checked on each pricing page.
- **The central claim:** that novices struggle with video, and that style reproduction is what closes the gap, is AutoHDR's account only. No source here measures it.
- None of these sources measures whether this product helps.

---

## References

1. HomeJab. Real Estate Photography Survey: 5 Surprising Stats. 2021. https://homejab.com/real-estate-photography-survey-5-surprising-stats/
2. WAV Group. HomeJab reveals top trends in pro real estate photos, video, 3D tours, aerial and more. 2021. https://www.wavgroup.com/2021/10/24/homejab-reveals-top-trends-in-pro-real-estate-photos-video-3d-tours-aerial-and-more/
3. Imagen AI. 10 Best Real Estate Video Editing Outsourcing Services in 2026. https://imagen-ai.com/post/real-estate-video-editing-outsourcing/ ; Fotober. Real Estate Video Pricing. https://fotober.com/real-estate-video-pricing
4. AutoReel vs Animoto. https://www.autoreelapp.com/compare/autoreel-vs-animoto ; Runway for real estate. https://runway.com/use-cases/real-estate

---

## 10. Assumptions made to proceed

No one at AutoHDR is available to ask, so these were decided instead of asked. Each can be reversed without changing who the user is.

| Gap | Assumption |
|---|---|
| What novices do today | They decline video, pay a freelance editor roughly $30–$150 per video, or use a generic template tool (Section 2). |
| "Nearly identical" | Same song and cut timing; the same type of camera movement in each shot; the "visibly AI-generated" line is the hard fail. Judged by the candidate and AutoHDR's reviewers watching the original and the reproduction side by side. |
| Style authoring | At least one authoring method works end to end, with 2–3 demo styles; the method is a design decision. |
| Failed shot | The video is still delivered with the failed shot marked and the reason shown. |
| What must not be lost | Uploads, saved styles and finished videos need only last through the demo. |
| Deadline and deliverable | 2026-10-21, 11:59 PM local time; a working demo plus the repo. |
| Web editor and marketplace | Not expected for this submission. |
| Hardware | No GPU relied on; hosted APIs. |
