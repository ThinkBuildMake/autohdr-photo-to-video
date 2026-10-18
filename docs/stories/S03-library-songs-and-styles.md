### S03 — Preset styles and Creative Commons songs can be listed, created and edited

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — five routes, two tables, a seed command and a licence rule
**Builds:** `songs` and `styles` write paths; listStyles `GET /api/styles`; getStyle `GET /api/styles/{id}`; listSongs `GET /api/songs`; createStyle `POST /api/styles`; updateStyle `PUT /api/styles/{id}`; Library interface getStyle and setReferenceJob; the songs seed command; Library's Must holds
**Extends:** none
**Stubs:** Files.presignDownload for song previews and the reference video — removed by S21; Photoshoots for `demoPhotoshootId` checks — removed by S25
**Requirements:** GC-5
**Supports:** FR-1.2, FR-2.1, FR-2.2, FR-2.5, FR-3.6 (shown in S21 and S25)
**Guards:** GC-5, FR-3.6, CH-1

#### Why
A style is a name, a written style and a song. This story stores them so the photographer can pick a preset and a style author can save one.

#### How it's checked
pytest against the routes with a test database, and the seed command run against a small song manifest.

#### Acceptance criteria
1. Seeding adds songs with their licence
   Given a manifest with one BY-NC track "Track A" by "Artist A"
   When the seed command runs
   Then `GET /api/songs` lists "Track A" with its licence, source URL and a credit line
2. A no-derivatives song is refused
   Given a manifest with a BY-NC-ND track
   When the seed command runs
   Then the track is not added and the command names it
3. A style is created
   Given the song "Track A"
   When `POST /api/styles` is sent with name "Golden hour", author "Sam", a style text and that song
   Then the answer is 201 with the style, fps 30 and no reference video
4. Presets list with their text and song
   Given the style "Golden hour"
   When `GET /api/styles` is called
   Then it lists "Golden hour" with its author, text, song and `hasReference` false
5. Empty text is refused
   Given the song "Track A"
   When `POST /api/styles` is sent with an empty style text
   Then the answer is 400 `invalid_style`
6. Frame rate is 24 or 30
   Given the song "Track A"
   When `POST /api/styles` is sent with fps 25
   Then the answer is 400 `invalid_style`
7. Names are unique
   Given the style "Golden hour"
   When another style named "Golden hour" is created
   Then the answer is 409 `name_taken`
8. A style is edited
   Given the style "Golden hour"
   When `PUT /api/styles/{id}` changes its text
   Then `GET /api/styles/{id}` returns the new text
9. An unknown style is reported
   Given no style with id `x`
   When `GET /api/styles/x` is called
   Then the answer is 404 `style_not_found`
10. A reference job is recorded
    Given the style "Golden hour"
    When setReferenceJob is called with a job id
    Then getStyle returns that job as its reference
11. A style holds text and a song only
    Given `POST /api/styles` sent with an extra field `videoUrl`
    When the style is created
    Then getStyle returns no video field

#### Not in this story
- Checking the reference job is ready and made from the style's text — picked up by S13
- Song preview links from the real bucket — picked up by S21
