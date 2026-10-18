### S05 — Photos are cropped to 16:9 and clips are cut to the song on time

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — six operations over Pillow, ffmpeg and the cut detector
**Builds:** Media interface crop16x9, thumbnail, extractFrames, probe, assemble, detectCuts; Media's Must hold (re-encoded cuts)
**Extends:** none
**Stubs:** none
**Requirements:** FR-1.4, DE-5, VR-2, VR-6
**Guards:** VR-2, DE-5

#### Why
Every shot starts from a 16:9 frame, and the finished video's cuts have to land where the plan says, at 1920 × 1080 and the style's frame rate.

#### How it's checked
pytest on generated test images, clips and a test tone, measuring the outputs with probe and detectCuts.

#### Acceptance criteria
1. Crop to 16:9
   Given a 4000 × 3000 JPEG
   When crop16x9 runs
   Then the result is 1920 × 1080
2. Thumbnail keeps the shape
   Given the same JPEG
   When thumbnail runs with a long side of 512
   Then the result is 512 × 384
3. Frames at a set rate
   Given a 4 s test clip
   When extractFrames runs at 6 per second
   Then it returns 24 frames
4. Assembly lands every cut within a frame
   Given three 4 s test clips with lengths 3.0, 2.5 and 3.5 s and cut transitions
   When assemble runs at 30 fps over a test tone
   Then detectCuts finds cuts at 3.0 s and 5.5 s, each within 1/30 s
5. Crossfades end at the cut
   Given two clips where the second has a 0.5 s crossfade and the first plays 3.0 s
   When assemble runs
   Then the second clip is fully on screen at 3.0 s
6. Output format
   Given any assembled video
   When probe runs on it
   Then it reports 1920 × 1080 at the requested 24 or 30 fps
7. The song starts at its offset
   Given a song offset of 12 s
   When assemble runs
   Then the video's audio matches the song from 12 s
8. Tool failures are reported
   Given a clip file that is not a video
   When assemble runs
   Then it raises MediaError with the tool's message

#### Not in this story
- Recording detected cuts against a plan — picked up by S13
