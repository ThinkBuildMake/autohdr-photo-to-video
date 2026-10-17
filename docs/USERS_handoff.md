# Handoff: design and requirement content removed from USERS.md

These items came up while defining the user but describe how the product is built, not who it serves. Carry them into requirements, metrics, stack and architecture. Each maps to a use case ID.

## Access and trust
- Demo-open: no login or accounts for now. (UC-1)

## Verification and honesty
- A shot that looks visibly AI-generated is the failing line. 1–2 per demo video are tolerated; zero is the target. (UC-1, UC-2)
- Wanted if possible: an ML check that catches bad shots and regenerates them before the user sees them. Who judges "visibly AI" is you and AutoHDR's reviewers. (UC-1)
- A shot that still fails after retries is shown to the user with which shot and why, never hidden. Whether the rest of the video is still delivered is open. (UC-1)
- Side-by-side comparison of the original and the reproduction is the test for style fidelity. "Nearly identical" is not yet a number. (UC-2)

## Capabilities traced to use cases
| Capability | Required by |
|---|---|
| Photo upload | UC-1 |
| Style library and selection | UC-1 |
| Style stored as a reusable storyboard of shots, each with a camera-movement prompt, a place in the song and a cut time (confirmed with the user as the working reading, 2026-10-17) | UC-2, UC-1 |
| Mapping a new shoot's photos into the style's shot slots | UC-1 |
| Photo enhancement toward the creator's composition, lens, angle, lighting | UC-1 |
| Keyframe-based video generation (first/last frame pinned to a shot) is a candidate method; the editor mockup shows Start Frame / End Frame fields | UC-1 |
| Cuts planned against the song's structure, e.g. an edit-plan structure listing which clip goes where in the audio | UC-1, UC-2 |
| Camera movement written as prompt text, per the PRD's starter kit; motion transfer from a reference video exists in some tools | UC-1, UC-2 |
| Automatic bad-shot detection and regeneration | UC-1 |
| Failure reporting per shot | UC-1 |
| Web editor with project file, optional | UC-3 (later) |

## Time budget
- 10–30 minutes of waiting is acceptable per video. (UC-1)
- Demo runs live if generation is fast enough, otherwise from a pre-generated run. (UC-1)

## Scope boundaries with their design reasons
- Desktop only: the PRD's mockups are desktop-style web screens and the user said to assume desktop.
- One user at a time: demo only; the candidate should still be able to explain how it would scale.
- Style authoring: the PRD gives three example methods and says it does not want to bias toward any. The choice is a design decision.
- "Train" a model on the style was raised by the user; the working reading is a stored style, not training. Confirm in the stack step.

## Open questions for the audit / research step
- Which video models are reachable from the approved-provider list or a free tier, and which accept first/last-frame or reference-video input? Verify in vendor docs; third-party blogs disagree and the tools change quickly.
- Whether generated shots can pass as non-AI is untested; check on the 12 sample photoshoots.
- Durability: what must never be lost (saved styles, uploads, finished videos) was not answered.
- Music: sources of Creative Commons non-commercial tracks and their attribution terms.
- Camera-movement vocabulary: the PRD's starter kit has a list of movement prompts; no independent source of per-shot template fields was found.

## Existing products in the same space
- Animoto: general slideshow maker; the nearest "template" alternative.
- Runway: generates camera motion from stills; the nearest "generate movement" alternative.
- AutoReel, Reel-E.ai: listing-specific photo-to-video makers.
- All unverified on their own pricing pages.
