# VIDEO_RESEARCH.md — Which video method works best for AutoHDR Photo-to-Video

**Status:** plan plus desk research. No experiment has been run, so nothing here says a method "works". Every claim from the web is tagged by source type. Vendor and blog pages are self-reported; the one academic source is a literature review.

**Question.** For a real-estate photoshoot and a stored style (song, shots, camera movements, cut times), which way of making each shot gives the most shots that do not look AI-generated, inside the 30-minute limit and the $0 budget?

**Why now.** `HIGH_LEVEL_DESIGN.md` treats the video service as one box. The choice of method decides the wireframe (does a shot have a start and end frame? a movement preset?), the entities (does a style hold a reference video?) and the stack. Requirements it must satisfy: VR-1 (≤ 2 visibly AI shots per video, target 0), VR-3 (same movement type as the original), VR-5 (rooms and fixtures unchanged), PF-1 (≤ 30 min), CO-1 / GC-3 ($0), GC-4 (approved providers or free tiers).

---

## 1. What the example prompt shows

The user found a creator who made a 20-second anime clip with an image model (GPT Image) for a character sheet and Seedance for the video. The prompt is useful less for its content than for its structure:

| Technique in the prompt | What it does | Use for us |
|---|---|---|
| A **reference sheet as the "sole visual authority"** (`@material:…` tag) | Locks identity across the whole clip | The source photo is the authority for the room. Lock rooms and fixtures the way it locks the costume (VR-5). |
| **Lock list**: "preserve exact …", "no new hairstyle, no duplicated character" | Names what must not change | A "room lock" paragraph: walls, windows, doors, furniture count, no new objects. |
| **Time-coded segments** (0–6 s, 6–8 s, …) with one action each | Directs pacing inside one generation | Maps onto a style's shots: each shot has a place in the song and a cut time. |
| **One continuous unbroken shot**, "no cuts, transitions" | Avoids the model inventing edits | Suggests one prompt per shot, and cutting ourselves to the song. |
| A **camera path described in order** ("rise above, curve down, arc around …") | Directs the move as a route | Camera movement as prompt text (matches the PRD starter kit). |
| **Clearance and safety rules** ("never intersect", "do not fly through") | Prevents geometry glitches | Same risk in rooms: camera must not pass through walls or furniture. |
| **A rule for what stays frozen**, plus "genuine 3-D parallax, not a flat still zoom" | Separates real motion from a cheap zoom | A test for us: the output must show parallax, not a Ken Burns zoom. |
| **Audio section** | The model makes sound too | We turn this off; the song comes from the repo (GC-5). |

Differences from our case: the example is stylised anime, one 20-second shot, with a character. Ours is photoreal interiors, several short shots cut to a song, and the failing line is "looks AI-generated". The example proves the control style, not the quality on houses.

## 2. What the desk research says so far

| Finding | Source type | Source |
|---|---|---|
| Seedance 2.0 accepts text, images, video and audio together; references are tagged in the prompt (`@Image1`, `@Video1`) with a role such as appearance or camera movement. Limits quoted: up to about 9 images, 3 videos, 3 audio clips. Clips about 4–15 s, 480p or 720p. | Third-party guides, limits disagree | [Together AI](https://www.together.ai/models/seedance-2-0), [Analytics Vidhya](https://www.analyticsvidhya.com/blog/2026/02/what-is-seedance-2-0/) |
| A reference video can drive camera movement; advice is to match the generation length to the reference's. No tested interior example found. | Blog | [Opus Pro](https://www.opus.pro/blog/replicate-camera-work-transitions-seedance) |
| For listing photos: use the delivered photo as the first frame, ask for slow gimbal or dolly moves, say "no shake". Energetic camera prompts read as a car advert. | Blogs | [VideoAI](https://videoai.me/blog/seedance-2-0-real-estate-prompts), [Segmind](https://blog.segmind.com/seedance-2-5-real-estate-video-every-shot-a-listing-needs/) |
| Two-endpoint (first and last frame) generation does not guarantee the middle respects room geometry; the middle needs checking frame by frame. | Blog | [Magic Hour](https://magichour.ai/blog/first-frame-last-frame-ai-video) |
| Make the last frame by editing the first, keep camera position and lens the same, avoid asking for wall or opening changes. Small drifts in window frames and wall lines show up once things move. | Blogs | [HeyGen](https://www.heygen.com/blog/how-we-made-it-the-furniture-unboxing), [ReRoom](https://es.reroom.ai/tutorial/how-to-turn-static-renders-into-ai-walkthrough-videos) |
| Frame-to-frame consistency of materials and structure still needs improvement in current text-to-video models. | Literature review (2024) | [arXiv 2404.01335](https://arxiv.org/pdf/2404.01335) |
| Veo 3.1 offers Ingredients to Video (several reference images), Frames to Video (start and end image) and Extend, all with audio. | Vendor announcement | [Google](https://blog.google/technology/ai/veo-updates-flow/) |
| Runway, Higgsfield: start/end frame, camera-move presets or motion controls, one clip at a time. | Third-party and vendor pages | see earlier notes in the session; unverified |
| Dreamina free tier: about 225 daily tokens, watermarked output, no card. Seedance API price per second differs by source ($0.02–$0.25). Whether Dreamina has an API is disputed. | Reseller blogs, conflicting | [Atlas Cloud](https://www.atlascloud.ai/blog/guides/how-to-use-seedance-2) |
| One creator's stack (self-reported, user-supplied): Seedance 2.0 / 2.5 for video, Midjourney for images, Claude for writing prompts and editing, ArtCraft / TapNow / Dreamina as platforms, Suno v6 for music. Same split as the others: images, video and prompt writing are separate tools. | Social post, unverified | user, 2026-10-17 |
| **Veo vs Seedance on realism.** Hands-on blog tests favour Veo 3.1 for faces, skin and light (one scorecard: 9.5 vs 8 out of 10), and say Seedance 2.0 is stronger on motion and multi-reference control. Blind-vote arena snapshots (Artificial Analysis, image-to-video with audio) put Seedance 2.0 near the top (about 1,176–1,199) and Veo 3.1 far below (about 1,078–1,094). The October 2026 snapshot shows a near tie among MiniMax H3 Max, Vidu Q4, Gemini Omni Flash and Seedance 2.0. The two kinds of evidence disagree; neither tested real-estate interiors. | Blogs (vendor-affiliated) and leaderboard snapshots via blogs | [Picsart](https://picsart.com/compare-models/seedance-2-0-vs-veo-3-1/), [SitePoint](https://www.sitepoint.com/seedance-2-0-vs-veo-3-1-which-is-best-for-ai-video-creators/), [benchmarklist](https://benchmarklist.com/arenas/artificial_analysis_image_to_video/) |
| **Veo access.** No free Gemini API tier for Veo 3.1. Flow reportedly gives 50 credits a day (about 5 Lite clips or 2 Fast clips), possibly only with a Google AI plan (Pro about $19.99/month). One source says the Veo 3.1 preview models on the Gemini API can shut down from 2026-10-22, one day after our deadline, with Gemini Omni Flash as the replacement. | Third-party pricing blogs, conflicting | [benchlm](https://benchlm.ai/media-pricing/veo), [camclo3d](https://camclo3d.com/blog/veo-3-pricing), [costgoat](https://costgoat.com/pricing/google-veo) |
| **Seedance face rule.** Seedance 2.0 reportedly blocks reference images with realistic human faces (deepfake filter); AI-generated and stylised faces pass. Listing photos rarely contain people, but any that do could be rejected. | Third-party docs and forum posts | [apiyi](https://docs.apiyi.com/en/faq/seedance2-asset-face-reference), [Luma](https://lumalabs.ai/learning-center/articles/seedance-2.0-basics) |
| Sora: reported discontinued in 2026 (app April, API September 24). | Roundup blog, unconfirmed | [TechSifted](https://techsifted.com/roundups/best-ai-video-generators-2026/) |
| Model naming is unstable: sources say "Seedance 2.0" and "2.5". | Blogs | same |

**What is not found:** any independent test of photoreal interiors with a "looks AI-generated" rating; official pricing for the Seedance API; whether a free tier covers 12 jobs; whether any approved-list provider (OpenAI, Midjourney, Google One) exposes video generation that fits GC-3.

## 3. Candidate methods

All six turn one source photo (after optional enhancement) into one shot. A video is the shots cut to the song, so only the shot method differs.

| ID | Method | Camera direction comes from | Also needs |
|---|---|---|---|
| M0 | **Baseline: no AI video.** Pan and zoom the photo (a slideshow with parallax if depth is estimated) | Preset move | Nothing. This is the honest fallback in USERS.md UC-1 and the floor the others must beat. |
| M1 | **Image-to-video, prompt only.** Photo as first frame, camera move as prompt text | Text prompt | A video model with image input |
| M2 | **First and last frame.** Photo is the first frame; the last frame is an edited version of it (closer, shifted) | Text prompt, plus the two frames | An image-edit model, and a video model that takes an end frame |
| M3 | **Reference-video motion.** Photo as first frame, the style's original shot as a motion reference | A clip of the original shot | A video model that takes a reference video (Seedance-style) |
| M4 | **Multi-reference, multi-shot in one generation.** Several photos tagged as references, time-coded prompt like the example, one clip for a whole sequence | Time-coded prompt | A model that accepts several references and long clips |

| M5 | **Cheap previz, then depth, then final render.** A fast, cheap model makes a rough draft of the shot (from the photo). The draft is converted to a depth map, and the expensive model renders the final shot from the draft and the real photo | The draft's motion, plus the depth map for structure | A cheap fast video model, a depth-estimation step, and a final model that takes the draft as a reference. Source: a creator's post (translated from Japanese) using MiniMax H3-max-turbo, then Seedance. Claimed benefits: cheap, fast iteration, natural camera work, background rebuilt cleanly, far fewer Seedance credits used. Self-reported, one anime example, not tested on interiors. |

Open questions for M5: (a) how the depth map is given to the final model (as a reference video is assumed, not confirmed); (b) the draft should come from the new photo, or the new house's rooms would be forced into the original's layout; (c) whether the cheap model is on the approved list or has a free tier.

Optional pre-step on any method: **P1 enhance** the photo toward the creator's composition and lighting (FR-1.8) with an image-edit model before it becomes the first frame. Tested as an on/off factor.

## 4. Experiment design

**Inputs (fixed, so methods are compared fairly).** 4 of the 12 test photoshoots (GC-6), chosen to vary: a bright open room, a dark room, a room with mirrors or glass, a small room (bathroom or hallway). 3 shots per shoot, one per movement type taken from the style (push-in, pan, tilt up). 12 shots per method, 6 methods, with and without P1 for the best two: roughly 96 generations. Raise to all 12 shoots only for the finalist.

**Prompt template (same for every model).** Four parts, as in the example:
1. Source: "Use the supplied photo as the sole visual authority for the room."
2. Room lock: "Do not add, remove or move walls, windows, doors, fixtures or furniture. No new objects."
3. Camera: one movement from the preset list, speed, "gimbal-smooth, no shake", clearance rule, framing rule.
4. Negatives: no cuts, no text, no audio (we supply the song).

**Measures.**

| Measure | How | Who or what | Maps to |
|---|---|---|---|
| Visibly AI-generated (warp, melt, morph) | Watch each shot; fail if any viewer-visible artifact | Reviewer (you), blind to which method made it | VR-1 |
| Room changed (added, removed or changed fixture or opening) | Compare first and last frames to the photo | Reviewer | VR-5 |
| Right movement type | Label the movement in each shot | Reviewer | VR-3 |
| Real parallax, not a flat zoom | Reviewer tick; also compare to M0 | Reviewer | quality |
| Automatic check agreement | Run the proposed quality check; compare flags with the reviewer's | System | QC-1 |
| Generation time per shot | Timestamps | System | PF-1 |
| Attempts to get a passing shot | Count regenerations until pass, max 3 | System | QC-2 |
| Free-tier use per shot | Provider usage page | System | CO-1, GC-3 |

The reviewer's rows stay human judgment, as in `KEY_METRICS.md`; the system rows can be logged.

**Decision rule (set before running).**
- A method is **eligible** if all of these hold on its 12 shots: ≤ 1 in 12 visibly AI after up to 3 regenerations, 0 room changes, 12 of 12 right movement type, median time per shot compatible with PF-1 (video of 8 shots done in ≤ 30 min), and no charge incurred.
- Among eligible methods, pick the one with the fewest regenerations; break ties by simplest design.
- If no AI method is eligible, ship M0 for the shots that fail and mark them (FR-1.5), and say so in the demo.
- The thresholds are proposals [prop] and follow VR-1's "target 0, up to 2 tolerated per video".

## 5. Order of work

1. **Access check (1 hour).** For each of Seedance (Dreamina), Veo (Flow or Google One), Runway, Kling, Higgsfield, and any OpenAI or Midjourney video feature: can I generate a 5-second clip from a photo today at $0, with what watermark, daily limit and length? Record in the table in §6. This decides which methods are even possible.
2. **Smoke test.** One shoot, M1 and M2 on one model by hand through its web UI. Expect to learn the prompt shape.
3. **Full matrix** on the 4 shoots for every method the access check allowed.
4. **Score**, apply the decision rule, write the result into §7.
5. **Feed back** into the wireframe, entities and stack (§8).

## 6. Shortlist and access table (to fill in step 1)

**Shortlist for the platform choice, 2026-10-17:** Seedance 2.0 (Dreamina), Veo 3.1 (Flow), and MiniMax H3 as the third because it tops the latest arena snapshot and is the cheap previz model in M5. Runway, Kling and Higgsfield stay in the table but are tested only if one of the three fails the access check. Sora is dropped (discontinued).

**Platform decision rule.** Run the same 12 shots (§4) on each shortlisted model through the method that model supports best. The platform with the most eligible results wins; a tie goes to the one that stays at $0 and has an API the worker can call (HLD §4.3). Blogs say Veo is more realistic and the blind arena says Seedance is, so the test on interiors decides, not either source.

| Model | Web UI free? | API free? | Max length | Resolution | Watermark | Daily limit | Start/end frame | Reference video | On approved list (GC-4) or free tier |
|---|---|---|---|---|---|---|---|---|---|
| Seedance via Dreamina | [to check] | [to check] | [to check] | | | | | | |
| Veo via Flow / Google One | | | | | | | | | |
| Runway | | | | | | | | | |
| Kling | | | | | | | | | |
| Higgsfield | | | | | | | | | |
| OpenAI / Midjourney video | | | | | | | | | |

## 7. Results

[Empty until the experiments run.]

## 8. What the result changes elsewhere

| If the winner is … | Changes |
|---|---|
| M2 (first and last frame) | Wireframe: shot cards show a start and an end frame. Entities: a Job shot has two image references. Stack: needs an image-edit model for the end frame. |
| M3 (reference video) | A Style stores a reference clip per shot, so "create a style" must cut the original into shots. Reference clips become files in storage. |
| M4 (multi-shot) | The unit of regeneration becomes a group of shots, not one shot; revisit FR-1.5 and QC-2 (per-shot failure reporting). |
| M0 (no AI) | The product is a styled slideshow. Revisit UC-1's honesty line and the demo story. |
| No access at $0 | Raise with the user: CO-1 and GC-3 rule out every method, so the design cannot meet them as written. |

## 9. Open items

| Item | Why it matters | Resolved by |
|---|---|---|
| "GPT Image 2" as named by the user was not verified | The image-edit model for P1 and M2 | Access check, §5 step 1 |
| Seedance API availability and price disputed | Decides whether it can run from the worker at all | Access check |
| An LLM could write each shot's prompt from the style shot and the photo; not yet a design box | Adds a step before the video service; Anthropic is on the approved list | Add to the next HLD revision if the experiments show prompt wording matters |
| Suno-generated music is not a Creative Commons track | GC-5 requires CC non-commercial tracks with source recorded | Keep repo tracks, or reword GC-5 after reading Suno's free-tier terms |
| ArtCraft, TapNow, Dreamina as access routes to Seedance: cost and API unknown | Decides how the worker can call the model | Access check, §5 step 1 |
| Model names and versions change quickly | Results expire | Record the model name and date with every result |
| Reviewer is one person | VR-1 is a human judgment; one rater is a weak sample | Use AutoHDR's reviewers' standard if known; otherwise state the limit |
